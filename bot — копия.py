import discord
from discord import app_commands
from discord.ext import commands, tasks
import a2s
import os
from dotenv import load_dotenv
import asyncio
import socket
from datetime import datetime
import pytz
from server_state import ServerState

# Загрузка переменных окружения
load_dotenv()

# Загрузка настроек из .env
TOKEN = os.getenv('DISCORD_TOKEN')
STATUS_CHANNEL_ID = int(os.getenv('STATUS_CHANNEL_ID'))
ADMIN_ROLE_ID = int(os.getenv('ADMIN_ROLE_ID'))
UPDATE_INTERVAL = int(os.getenv('UPDATE_INTERVAL', '10'))
MAX_PLAYERS_SHOW = int(os.getenv('MAX_PLAYERS_SHOW', '30'))
BOT_STATUS = os.getenv('BOT_STATUS', 'губешкой')
INFO_TIMEOUT = float(os.getenv('INFO_TIMEOUT', '3.0'))
PLAYERS_TIMEOUT = float(os.getenv('PLAYERS_TIMEOUT', '7.0'))

if TOKEN is None:
    raise ValueError("Токен Discord не найден в файле .env!")

# ANSI цвета
COLORS = {
    'red': '\u001b[31m',
    'green': '\u001b[32m',
    'yellow': '\u001b[33m',
    'blue': '\u001b[34m',
    'magenta': '\u001b[35m',
    'cyan': '\u001b[36m',
    'white': '\u001b[37m',
    'reset': '\u001b[0m'
}

class GModServer:
    def __init__(self):
        self.address = None
        self.port = None
        self.status_message = None
        self.last_player_count = 0
        self.last_change_time = None
        self.server_name = None
        self.message_id = None
        self.channel_id = None

    def set_server(self, address, port):
        """Настройка сервера с сохранением текущего имени"""
        old_name = self.server_name
        self.address = address
        self.port = port
        self.status_message = None
        self.last_player_count = 0
        self.last_change_time = None
        self.server_name = old_name

    def is_configured(self):
        return self.address is not None and self.port is not None

    def update_player_count(self, new_count):
        if new_count != self.last_player_count:
            self.last_player_count = new_count
            self.last_change_time = datetime.now()
            return True
        return False

    def update_server_name(self, name):
        """Обновляем имя сервера"""
        if name:
            self.server_name = name

    def format_player_info(self, player):
        """Форматирование информации об игроке"""
        minutes = int(player.duration//60)
        return f"║ {COLORS['yellow']}{minutes:3d} мин.{COLORS['reset']} | {COLORS['cyan']}{player.name}{COLORS['reset']}\n"

    def format_long_text(self, text, max_length=75):
        """Форматирует длинный текст, разбивая его на строки"""
        if len(text) <= max_length:
            return text
        
        parts = []
        current_part = ""
        words = text.split('/')
        
        for word in words:
            if len(current_part) + len(word) + 1 <= max_length:
                current_part += ('/' if current_part else '') + word
            else:
                if current_part:
                    parts.append(current_part)
                current_part = word
        
        if current_part:
            parts.append(current_part)
            
        return '\n║         '.join(parts)

    def get_server_url(self):
        """Генерирует ссылку на сервер на tsarvar.com"""
        return f"https://tsarvar.com/ru/servers/garrys-mod/{self.address}:{self.port}"

    def calculate_message_length(self, header, players_info, footer, remaining_info=""):
        """Подсчет длины сообщения"""
        return len(header) + len(players_info) + len(footer) + len(remaining_info)

    def format_time_since_change(self):
        """Форматирует время с последнего изменения"""
        if not self.last_change_time:
            return "Последнее изменение: никогда"
        
        now = datetime.now()
        diff = now - self.last_change_time
        
        if diff.total_seconds() < 60:
            return f"Последнее изменение: {int(diff.total_seconds())} сек. назад"
        elif diff.total_seconds() < 3600:
            return f"Последнее изменение: {int(diff.total_seconds() // 60)} мин. назад"
        else:
            hours = int(diff.total_seconds() // 3600)
            return f"Последнее изменение: {hours} ч. назад"

class GModBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='/', intents=intents)
        self.servers = {}
        self.server_state = ServerState()
        self.add_commands()
        
    def get_server_id(self, address, port):
        """Генерирует уникальный ID сервера"""
        return f"{address}:{port}"

    def add_server(self, address, port):
        """Добавляет новый сервер для мониторинга"""
        server_id = self.get_server_id(address, port)
        if server_id in self.servers:
            return False, "Этот сервер уже отслеживается"
        
        server = GModServer()
        server.set_server(address, port)
        self.servers[server_id] = server
        return True, "Сервер успешно добавлен"

    def remove_server(self, address, port):
        """Удаляет сервер из мониторинга"""
        server_id = self.get_server_id(address, port)
        if server_id not in self.servers:
            return False, "Этот сервер не отслеживается"
        
        server = self.servers[server_id]
        if server.status_message:
            asyncio.create_task(server.status_message.delete())
        
        # Удаляем информацию о сервере из состояния
        self.server_state.remove_server(server_id)
        del self.servers[server_id]
        return True, "Сервер успешно удален"

    def add_commands(self):
        @self.tree.command(name="connect", description="Добавить сервер для мониторинга")
        async def connect_command(interaction: discord.Interaction, server_address: str):
            if not self.has_admin_role(interaction.user):
                await interaction.response.send_message("❌ У вас нет прав!", ephemeral=True)
                return
                
            try:
                address, port = server_address.split(':')
                port = int(port)
                success, message = self.add_server(address, port)
                await interaction.response.send_message(
                    f"{'✅' if success else '❌'} {message}",
                    ephemeral=True
                )
            except ValueError:
                await interaction.response.send_message(
                    "❌ Неверный формат адреса. Используйте формат ip:port",
                    ephemeral=True
                )

        @self.tree.command(name="stop", description="Остановить мониторинг сервера")
        async def stop_command(interaction: discord.Interaction, server_address: str):
            if not self.has_admin_role(interaction.user):
                await interaction.response.send_message("❌ У вас нет прав!", ephemeral=True)
                return
                
            try:
                address, port = server_address.split(':')
                port = int(port)
                success, message = self.remove_server(address, port)
                await interaction.response.send_message(
                    f"{'✅' if success else '❌'} {message}",
                    ephemeral=True
                )
            except ValueError:
                await interaction.response.send_message(
                    "❌ Неверный формат адреса. Используйте формат ip:port",
                    ephemeral=True
                )

        @self.tree.command(name="list", description="Показать список отслеживаемых серверов")
        async def list_command(interaction: discord.Interaction):
            if not self.has_admin_role(interaction.user):
                await interaction.response.send_message("❌ У вас нет прав!", ephemeral=True)
                return
                
            if not self.servers:
                await interaction.response.send_message("ℹ️ Нет отслеживаемых серверов", ephemeral=True)
                return
                
            server_list = "\n".join([
                f"📍 {server_id}" + 
                (f" - {server.server_name}" if server.server_name else "")
                for server_id, server in self.servers.items()
            ])
            await interaction.response.send_message(
                f"📋 Отслеживаемые сервера:\n{server_list}",
                ephemeral=True
            )

    @tasks.loop(seconds=UPDATE_INTERVAL)
    async def update_status(self):
        """Обновляет статус всех серверов"""
        servers_copy = dict(self.servers)
        for server_id, server in servers_copy.items():
            try:
                print(f"\n[Обновление] Начало обновления для сервера {server_id}")
                await self.check_server_status(server)
            except Exception as e:
                print(f"[Ошибка] При обновлении сервера {server_id}: {e}")

    async def setup_hook(self):
        print("Запуск задачи обновления статуса...")
        self.update_status.start()
        print("Синхронизация команд...")
        try:
            synced = await self.tree.sync()
            print(f"Синхронизировано {len(synced)} команд")
        except Exception as e:
            print(f"Ошибка при синхронизации команд: {e}")

    def has_admin_role(self, user):
        """Проверяет наличие роли администратора у пользователя"""
        if not user.guild:
            return False
        return any(role.id == ADMIN_ROLE_ID for role in user.roles)

    async def check_server_status(self, server):
        """Проверяет статус сервера и обновляет сообщение"""
        channel = self.get_channel(STATUS_CHANNEL_ID)
        if not channel:
            print(f"[Ошибка] Не удалось найти канал {STATUS_CHANNEL_ID}")
            return

        server_id = self.get_server_id(server.address, server.port)
        stored_server_info = self.server_state.get_server_info(server_id)

        print(f"[Сервер {server_id}] Начало проверки статуса")
        try:
            # Инициализируем переменные для сообщения
            message = "```ansi\n"
            header = message + "╔════════════════════════════════════════════╗\n"
            header += "║          \u001b[1;33mИнформация о сервере\u001b[0m              ║\n"
            header += "╠════════════════════════════════════════════╣\n"
            players_info = ""
            footer = "╚════════════════════════════════════════════╝\n```"
            
            # Добавляем счетчик попыток
            max_retries = 2
            retry_delay = 1  # секунды между попытками
            server_info = None
            server_players = None
            
            # Пытаемся получить информацию о сервере
            for attempt in range(max_retries):
                try:
                    print(f"[Сервер {server_id}] Попытка {attempt + 1}/{max_retries} получения информации")
                    socket.setdefaulttimeout(INFO_TIMEOUT)
                    address = (server.address, server.port)
                    server_info = a2s.info(address)
                    
                    socket.setdefaulttimeout(PLAYERS_TIMEOUT)
                    server_players = a2s.players(address)
                    
                    # Если успешно получили информацию, выходим из цикла
                    break
                    
                except (socket.timeout, ConnectionRefusedError, OSError) as e:
                    print(f"[Сервер {server_id}] Попытка {attempt + 1}/{max_retries} не удалась: {str(e)}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
            
            # Если не удалось получить информацию после всех попыток
            if server_info is None:
                print(f"[Сервер {server_id}] Сервер недоступен после всех попыток")
                server_url = server.get_server_url()
                # Для оффлайн режима используем длинную рамку
                message = "```ansi\n"
                header = message + "╔═══════════════════════════════════════════════════════════════════════════════════╗\n"
                header += "║                              \u001b[1;33mИнформация о сервере\u001b[0m                                 ║\n"
                header += "╠═══════════════════════════════════════════════════════════════════════════════════╣\n"
                header += f"║ \u001b[1;36mНазвание:\u001b[0m \u001b[1;34m{server_url}\u001b[0m\n"
                header += f"║ \u001b[1;36mIP:\u001b[0m {server.address}:{server.port}\n"
                header += f"║ \u001b[1;36mСтатус:\u001b[0m \u001b[1;31mОффлайн\u001b[0m\n"
                header += "╠═══════════════════════════════════════════════════════════════════════════════════╣\n"
                header += "║                                \u001b[1;33mСтатус сервера\u001b[0m                                     ║\n"
                header += "╠═══════════════════════════════════════════════════════════════════════════════════╣\n"
                header += "║ \u001b[1;31mСервер временно недоступен\u001b[0m\n"
                header += f"║ \u001b[1;31mДанные были обновлены: {datetime.now(pytz.timezone('Europe/Moscow')).strftime('%H:%M:%S')}\u001b[0m\n"
                footer = "╚═══════════════════════════════════════════════════════════════════════════════════╝\n```"
                message = header + footer
                
                # Обновляем или отправляем сообщение
                try:
                    if stored_server_info and stored_server_info.get("message_id"):
                        try:
                            print(f"[Сервер {server_id}] Попытка обновления существующего сообщения")
                            msg = await channel.fetch_message(int(stored_server_info["message_id"]))
                            await msg.edit(content=message)
                            print(f"[Сервер {server_id}] Сообщение успешно обновлено")
                        except (discord.NotFound, discord.HTTPException, discord.Forbidden):
                            print(f"[Сервер {server_id}] Сообщение не найдено, создаем новое")
                            new_message = await channel.send(message)
                            self.server_state.update_message_id(server_id, new_message.id)
                            print(f"[Сервер {server_id}] Новое сообщение создано")
                    else:
                        print(f"[Сервер {server_id}] Создание нового сообщения")
                        new_message = await channel.send(message)
                        self.server_state.add_server(server_id, new_message.id, channel.id, server.server_name or "Неизвестный сервер")
                        print(f"[Сервер {server_id}] Новое сообщение создано")
                except Exception as e:
                    print(f"[Сервер {server_id}] Ошибка при отправке сообщения об оффлайн статусе: {str(e)}")
                return
            
            # Если мы здесь, значит успешно получили информацию
            try:
                player_count_changed = server.update_player_count(server_info.player_count)
                change_message = ""
                if player_count_changed:
                    change_type = "➕" if server_info.player_count > server.last_player_count else "➖"
                    change_message = f"║ \u001b[1;35m{change_type} Количество игроков изменилось\u001b[0m\n"
                
                header += f"║ \u001b[1;36mНазвание:\u001b[0m {server_info.server_name}\n"
                header += f"║ \u001b[1;36mКарта:\u001b[0m {server_info.map_name}\n"
                header += f"║ \u001b[1;32mIP:\u001b[0m {server.address}:{server.port}\n"
                header += f"║ \u001b[1;32mИгроки:\u001b[0m {server_info.player_count}/{server_info.max_players}\n"
                header += f"║ {server.format_time_since_change()}\n"
                header += "╠════════════════════════════════════════════╣\n"
                
                server.update_server_name(server_info.server_name)
                
                if server_players:
                    players_info += "║            \u001b[1;33mСписок игроков\u001b[0m                  ║\n"
                    players_info += "╠════════════════════════════════════════════╣\n"
                    valid_players = [p for p in server_players if p.name]
                    if valid_players:
                        sorted_players = sorted(valid_players, key=lambda x: x.duration, reverse=True)
                        
                        temp_players_info = ""
                        displayed_count = 0
                        remaining_players = len(sorted_players)
                        
                        for player in sorted_players:
                            player_line = server.format_player_info(player)
                            message_length = server.calculate_message_length(header, players_info + temp_players_info + player_line + change_message, footer)
                            
                            if message_length >= 1900 or displayed_count >= MAX_PLAYERS_SHOW:
                                remaining_players = len(sorted_players) - displayed_count
                                break
                            
                            temp_players_info += player_line
                            displayed_count += 1
                        
                        players_info += temp_players_info
                        
                        if remaining_players > displayed_count:
                            players_info += "╠════════════════════════════════════════════╣\n"
                            players_info += f"║ \u001b[1;35mИ ещё {remaining_players - displayed_count} игроков\u001b[0m\n"
                        
                        if change_message:
                            players_info += "║\n"
                            players_info += change_message
                    else:
                        players_info += "║ \u001b[1;31mСервер пуст\u001b[0m\n"
                else:
                    players_info += "║ \u001b[1;31mСервер пуст\u001b[0m\n"
                    
            except Exception as e:
                print(f"[Сервер {server_id}] Ошибка при обработке данных сервера: {str(e)}")
                return
            
            message = header + players_info + footer
            
            # Обновляем или отправляем сообщение
            try:
                if stored_server_info and stored_server_info.get("message_id"):
                    try:
                        print(f"[Сервер {server_id}] Попытка обновления существующего сообщения")
                        msg = await channel.fetch_message(int(stored_server_info["message_id"]))
                        await msg.edit(content=message)
                        print(f"[Сервер {server_id}] Сообщение успешно обновлено")
                    except (discord.NotFound, discord.HTTPException, discord.Forbidden):
                        print(f"[Сервер {server_id}] Сообщение не найдено, создаем новое")
                        new_message = await channel.send(message)
                        self.server_state.update_message_id(server_id, new_message.id)
                        print(f"[Сервер {server_id}] Новое сообщение создано")
                else:
                    print(f"[Сервер {server_id}] Создание нового сообщения")
                    new_message = await channel.send(message)
                    self.server_state.add_server(server_id, new_message.id, channel.id, server_info.server_name)
                    print(f"[Сервер {server_id}] Новое сообщение создано")
            except Exception as e:
                print(f"[Сервер {server_id}] Ошибка при отправке сообщения: {str(e)}")
                
        except Exception as e:
            print(f"[Сервер {server_id}] Ошибка при проверке статуса сервера: {str(e)}")
            # Если произошла ошибка подключения к Discord, просто логируем и продолжаем
            pass

    async def on_ready(self):
        """Обработчик события готовности бота"""
        print(f'Бот {self.user} готов к работе!')
        activity = discord.Activity(type=discord.ActivityType.playing, name=BOT_STATUS)
        await self.change_presence(activity=activity)

        # Восстанавливаем состояние серверов при запуске
        for server_id, server_info in self.server_state.get_all_servers().items():
            try:
                address, port = server_id.split(':')
                port = int(port)
                success, _ = self.add_server(address, port)
                if success:
                    print(f"[Восстановление] Сервер {server_id} успешно восстановлен")
            except Exception as e:
                print(f"[Восстановление] Ошибка при восстановлении сервера {server_id}: {e}")

bot = GModBot()
bot.run(TOKEN)
