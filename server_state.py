import json
import os
from datetime import datetime
from typing import Dict, Optional

class ServerState:
    def __init__(self, state_file: str = "server_state.json"):
        self.state_file = state_file
        self.servers: Dict[str, dict] = {}
        self.load_state()

    def load_state(self) -> None:
        """Загружает состояние из JSON файла"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    self.servers = json.load(f)
            except json.JSONDecodeError:
                print("Ошибка при чтении файла состояния. Создаем новый.")
                self.servers = {}
        else:
            self.servers = {}

    def save_state(self) -> None:
        """Сохраняет состояние в JSON файл"""
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.servers, f, indent=4, ensure_ascii=False)

    def add_server(self, server_id: str, message_id: int, channel_id: int, server_name: str) -> None:
        """Добавляет или обновляет информацию о сервере"""
        self.servers[server_id] = {
            "message_id": str(message_id),
            "channel_id": str(channel_id),
            "server_name": server_name,
            "last_update": datetime.now().isoformat()
        }
        self.save_state()

    def remove_server(self, server_id: str) -> None:
        """Удаляет информацию о сервере"""
        if server_id in self.servers:
            del self.servers[server_id]
            self.save_state()

    def get_server_info(self, server_id: str) -> Optional[dict]:
        """Получает информацию о сервере"""
        return self.servers.get(server_id)

    def update_message_id(self, server_id: str, new_message_id: int) -> None:
        """Обновляет ID сообщения для сервера"""
        if server_id in self.servers:
            self.servers[server_id]["message_id"] = str(new_message_id)
            self.servers[server_id]["last_update"] = datetime.now().isoformat()
            self.save_state()

    def get_all_servers(self) -> Dict[str, dict]:
        """Возвращает информацию о всех серверах"""
        return self.servers.copy() 