import sqlite3, yaml, requests, os, glob, schedule, threading, time, zipfile, datetime
import re, traceback, platform
from typing import List, Optional, Tuple, Dict
import asyncio, aiosqlite, base64, aiofiles
from cachetools import TTLCache
from export_excel import start_export

class LogSystem:
    def __init__(self, db_name: str = "database", style_name: str = "normal", styles: str = "styles", image: str = r"static\images\logs", backup : str = "backup"):
        """
        初始化日志系统
        """

        # 5分钟的缓存，用于告诉网页端是否需要刷新页面
        self.cache = TTLCache(maxsize=10, ttl=300)

        self.db_name = f'{db_name}.db'
        self._init_database()
        self._permanently_enable_wal()
        self.bot = None

        self.image = image
        if not os.path.exists(self.image):
            os.makedirs(self.image)
        
        self.nostyle = False
        self.style_name = style_name
        self.styles = styles
        if not os.path.exists(self.styles):
            os.makedirs(self.styles)
        self.style = self.read_config(style_name)

        self.backup_running = False
        self.backup_thread = None
        self.now_backup = False
        self.backup = backup
        if not os.path.exists(self.backup):
            os.makedirs(self.backup)

    def bot_init(self, bot, needreload: bool = False):
        self.bot = bot
        if needreload:
            self.db_name = f'{bot.config.get("db_name")}.db'
            self.image = bot.config.get("image")
            if self.style_name != bot.config.get("style"):
                self.style_name = bot.config.get("style")
                self.style = self.read_config(self.style_name)
            self.backup = bot.config.get("backup_file")
        self.start_backup_scheduler()
    
    def read_config(self, config_path="normal"):
        """读取配置文件"""
        path = os.path.join(self.styles, f'{config_path}.yml')
        try:
            with open(path, 'r', encoding='utf-8') as file:
                style = yaml.safe_load(file)
                self.style_name = config_path
                self.nostyle = False

                # 如果加载的风格文件和config.yml中记的不一样，就更新config.yml中记的为当前的风格文件名字
                if self.bot and self.bot.config.get("style", None) != config_path:
                    self.bot.config["style"] = config_path
                    self.bot.update_config(self.bot.config)

                return style
        except FileNotFoundError:
            self.nostyle = self.style.get("style_not_found").format(name=config_path) if self.style and self.style.get("style_not_found") else f"风格文件 {config_path} 不存在"
            return None
        except yaml.YAMLError as e:
            self.nostyle = self.style.get("style_load_error").format(e=e) if self.style and self.style.get("style_load_error") else f"解析风格文件出错: {str(e)}"
            return None

    def _init_database(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            # 创建日志表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    operator TEXT,
                    duration TEXT,
                    group_id TEXT NOT NULL,
                    time TIMESTAMP DEFAULT (datetime('now', 'localtime'))
                )
            ''')
            # 创建索引以提高查询性能
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_target ON logs (target)')
            conn.commit()
    
    def _permanently_enable_wal(self): 
        """启用WAL模式"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            current_mode = cursor.fetchone()[0]
            if current_mode.upper() != "WAL":
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                print("数据库已永久启用WAL模式")

    def start_backup_scheduler(self, now_time = None):
        """启动备份调度器"""

        if self.backup_running:
            return self.style.get("backup_auto_open")

        if now_time is None:
            now_time = (datetime.datetime.now() + datetime.timedelta(minutes=1)).strftime("%H:%M")
            
        self.stop_event = threading.Event()
        def scheduler_loop():
            self.backup_running = True

            # 每天检查一次是否需要备份
            schedule.every().day.at(now_time).do(self.check_and_backup)

            print(f"📅 备份调度器已启动，每天{now_time}检查备份")
            
            while not self.stop_event.is_set():
                if not self.now_backup:
                    schedule.run_pending()
                self.stop_event.wait(timeout=60)
        
        # 在新线程中运行
        self.backup_thread = threading.Thread(target=scheduler_loop, daemon=True)
        self.backup_thread.start()
        return self.style.get("backup_auto_open")

    def stop_backup_scheduler(self):
        """停止备份调度器"""

        if not self.backup_running:
            return self.style.get("backup_auto_close")
        print("正在停止备份调度器...")
        self.backup_running = False
        self.stop_event.set()
        if self.backup_thread and self.backup_thread.is_alive():
            self.backup_thread.join(timeout=5)
            
            if self.backup_thread.is_alive():
                print("⚠️  线程未正常结束，强制清理")
            else:
                print("✅ 备份调度器已停止")
        
        schedule.clear()
        self.backup_thread = None
        return self.style.get("backup_auto_close")

    def check_and_backup(self):
        """检查上次备份时间间隔并执行备份"""

        if self.now_backup:
            return
        self.now_backup = True

        now_time = datetime.datetime.now()
        first_backup = False
        backup_time = self.bot.config.get("backup_time", None)
        last_time = None

        # 检查获取备份时间，是否是初次备份
        if backup_time:
            last_time = datetime.datetime.strptime(backup_time, "%Y-%m-%d %H:%M:%S")
        else:
            first_backup = True

        # 初次备份或备份时间达到备份间隔
        if first_backup or (now_time - last_time).days >= self.bot.config.get("backup_delay", 7):

            # 开始备份
            respond = self.backup_without_locks(now_time.strftime('%Y%m%d_%H%M%S'))

            # 更新配置文件中的上次备份时间
            self.bot.config["backup_time"] = now_time.strftime("%Y-%m-%d %H:%M:%S")
            self.bot.update_config(self.bot.config)

            # 删除超过上限的最旧备份
            backups = self.get_backup_files_sorted()
            while len(backups) > self.bot.config.get("backup_limit"):
                message = self.delete_file(backups[0])
                backups[0] = None
                respond = f"{respond}\n{message}"
            
            message = respond

            # 下载群聊头像
            # if not os.path.exists(os.path.join(self.image, "groups")):
            #     os.makedirs(os.path.join(self.image, "groups"))
            # for i, group in self.style.get("qq_groups").items():
            #     url = self.bot.get_group_avatar_url(i)
            #     ifimage = self.download_image(url, os.path.join("groups", str(i)), self.bot.config.get("groups"))
            #     message = f'{message}\n{ifimage if ifimage else self.style.get("download_groups_image_succeess").format(group_id=f"{i}（{group}）")}'

            success = start_export()
            message = f"{message}\n{self.style.get("export_excel_success") if success else self.style.get("export_excel_error")}{1}"
            response = self.bot.send_group_message(self.bot.config.get("QQgroup"), message)

        self.now_backup = False
    
    def backup_without_locks(self, name: None):
        """使用SQLite的API在线备份"""

        if name is None:
            name = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

        backup_path = os.path.join(self.backup, self.db_name)
        
        try:
            # 连接到主数据库
            source = sqlite3.connect(self.db_name, timeout=30)
            source.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # 清理WAL文件
            
            # 创建备份数据库
            target = sqlite3.connect(backup_path)
            
            # 执行在线备份
            # 这个方法允许在备份期间继续读写
            source.backup(target, name='main', pages=5, sleep=0.25)
            
            source.close()
            target.close()
            
            # 验证备份完整性
            e = self.verify_backup(backup_path)
            if not e:
                print(f"在线备份成功: {backup_path}")
                return self.create_zip_backup(name)
            else:
                os.remove(backup_path)
                return self.style.get("backup_verify_error").format(e=e)
                
        except sqlite3.Error as e:
            print(f"在线备份失败: {e}")
            return self.style.get("backup_make_error").format(e=e)
    
    def verify_backup(self, backup_path):
        """验证备份文件的完整性"""
        try:
            conn = sqlite3.connect(backup_path)
            cursor = conn.cursor()
            
            # 检查表结构
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            
            # 检查数据完整性
            cursor.execute("SELECT COUNT(*) FROM logs")
            count = cursor.fetchone()[0]
            
            # 尝试执行一些查询
            cursor.execute("SELECT 1 FROM logs LIMIT 1")
            
            conn.close()
            print(f"备份验证通过: {len(tables)}个表，{count}条记录")
            return False
            
        except Exception as e:
            print(f"备份验证失败: {e}")
            return e
        
    def create_zip_backup(self, name):
        """
        将db和image文件夹压缩为最小体积的zip包
        
        Args:
            name: 压缩包名称（不需要.zip后缀）
        
        Returns:
            str: 生成的压缩包路径，失败返回None
        """

        try:
            # 准备路径
            backup_dir = self.backup
            db_file = os.path.join(backup_dir, self.db_name)
            image_dir = self.image
            zip_filename = f"{name}.zip"
            zip_path = os.path.join(backup_dir, zip_filename)
            
            print(f"🎯 开始创建压缩包: {zip_filename}")
            
            # 创建压缩包（使用ZIP_DEFLATED获得最小体积）
            print("📦 创建压缩文件...")
            with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
                
                # 压缩数据库文件
                print(f"  添加数据库文件: {name}")
                zipf.write(db_file, arcname=self.db_name)
                
                # 3.2 压缩image文件夹（如果存在）
                if os.path.exists(image_dir) and os.path.isdir(image_dir):
                    print(f"  添加image文件夹内容...")
                    for root, _, files in os.walk(image_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            
                            # 计算在zip中的相对路径
                            arcname = os.path.relpath(file_path, os.path.dirname(image_dir))
                            
                            # 添加到压缩包
                            zipf.write(file_path, arcname=arcname)
            
            # 删除原始的db文件
            try:
                os.remove(db_file)
                print(f"🗑️  已删除原始数据库文件: {db_file}")
            except Exception as e:
                return self.style.get("backup_delete_error").format(e=e)
            
            return self.style.get("backup_make_success").format(name=zip_filename)
            
        except Exception as e:
            traceback.print_exc()
            return self.style.get("backup_zip_error").format(e=e)
        
    def extract_zip(self, file):
        """
        解压压缩包并替换到脚本所在目录
        
        Args:
            zip_path: 压缩包文件路径
        
        Returns:
            bool: 成功返回True，失败返回False
        """
        
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        # 获取当前脚本所在目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        zip_file = os.path.join(self.backup, file)
        try:
            # 打开zip文件
            with zipfile.ZipFile(zip_file, 'r') as z:
                # 解压所有内容到当前目录
                z.extractall(current_dir)
                
            return self.style.get("backup_back_success").format(path=file)
            
        except FileNotFoundError:
            return self.style.get("backup_file_not_found").format(path=zip_file)
        except Exception as e:
            return self.style.get("backup_back_error").format(e=e)
    
    def get_backup_files_sorted(self, backup_dir: str = None):
        """
        获取文件夹内所有文件（按修改时间从小到大排序）
        
        Args:
            backup_dir: 备份文件夹路径，默认为"backup"
        
        Returns:
            list: 按修改时间从小到大排序的文件路径列表
        """

        if backup_dir is None:
            backup_dir = self.backup
        
        # 检查文件夹是否存在
        if not os.path.exists(backup_dir):
            print(f"文件夹不存在: {backup_dir}")
            return []
        
        if not os.path.isdir(backup_dir):
            print(f"路径不是文件夹: {backup_dir}")
            return []
        
        # 获取所有文件（排除子文件夹）
        files = []
        for item in os.listdir(backup_dir):
            item_path = os.path.join(backup_dir, item)
            if os.path.isfile(item_path):  # 只处理文件，不处理文件夹
                files.append(item_path)
        
        # 按修改时间排序（从小到大，即最旧的在前）
        files.sort(key=os.path.getmtime)
        for i, value in enumerate(files):
            files[i] = os.path.basename(value)
        
        return files

    def delete_file(self, file_path: str) -> str:
        """
        删除指定路径的文件
        
        Args:
            file_path: 要删除的文件的完整路径或相对路径
            
        Returns:
            str: 回复消息
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                return self.style.get("backup_file_not_found").format(path=file_path)
            
            # 删除文件
            os.remove(file_path)
            return self.style.get("backup_delete_success").format(path=os.path.basename(file_path))
            
        except OSError as e:
            return self.style.get("backup_delete_error").format(e=e)
    
    def download_image(self, url, base_name, path = None):
        """下载图片"""

        path = self.bot.config.get("image") if path is None else path
        try:
            # 发送GET请求获取图片
            response = requests.get(url)
            
            # 检查请求是否成功
            if response.status_code != 200:
                return self.style.get("download_image_response_status_code").format(response=response.status_code)
            
            # 从Content-Type获取扩展名
            content_type = response.headers.get('Content-Type', '')
            
            if 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            elif 'png' in content_type:
                ext = '.png'
            elif 'gif' in content_type:
                ext = '.gif'
            else:
                ext = '.jpg'  # 默认
            
            filename = f"{base_name}{ext}"
            
            # 写入文件
            if not os.path.exists(self.image):
                os.makedirs(self.image)
            with open(os.path.join(path, filename), 'wb') as f:
                f.write(response.content)
            
            return False
        except Exception as e:
            return self.style.get("download_image_error").format(e=str(e))
    
    def validate_time_with_detail(self, time_str):
        """验证时间并给出具体错误原因"""
        try:
            target_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            current_time = datetime.datetime.now()
            if target_time > current_time:
                return self.style.get("time_error9")
            return False
        
        except ValueError as e:
            error_msg = str(e)
            
            # 分析错误信息
            if "unconverted data remains" in error_msg:
                return self.style.get("time_error1")
            elif "does not match format" in error_msg:
                return self.style.get("time_error2")
            elif "day is out of range" in error_msg:
                return self.style.get("time_error3")
            elif "month must be in 1..12" in error_msg:
                return self.style.get("time_error4")
            elif "hour must be in 0..23" in error_msg:
                return self.style.get("time_error5")
            elif "minute must be in 0..59" in error_msg:
                return self.style.get("time_error6")
            elif "second must be in 0..59" in error_msg:
                return self.style.get("time_error7")
            elif "microsecond must be in 0..999999" in error_msg:
                return self.style.get("time_error8")
            else:
                return self.style.get("time_error").format(e=error_msg)
            
    def check_filename(self, filename: str) -> str:
        """
        检查字符串是否可以作为有效的文件名
        
        Args:
            filename: 要检查的字符串
            
        Returns:
            message: 回复消息
        """

        # 长度检查
        l = len(filename)
        if l > 255:
            return self.style.get("backup_name_error6").format(l=l)
        
        # 系统保留字符检查（跨平台）
        # Windows和Unix/Linux/macOS都禁止的字符
        reserved_chars = r'[<>:"/\\|?*\x00-\x1F]'  # \x00-\x1F 是控制字符
        if re.search(reserved_chars, filename):
            return self.style.get("backup_name_error").format(name=filename)
        
        system = platform.system()
        
        # Windows保留名称
        if system == "Windows":
            windows_reserved = [
                "CON", "PRN", "AUX", "NUL",
                "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
                "LPT1", "LPT2", "PT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
            ]
            # Windows不区分大小写
            if filename.upper() in windows_reserved:
                return self.style.get("backup_name_error2").format(name=filename)
            
            # Windows文件名不能以空格或点结尾
            if filename.rstrip() != filename:
                return self.style.get("backup_name_error3").format(name=filename)
        
        # 特定位置字符检查
        if filename == "." or filename == "..":
            return self.style.get("backup_name_error4").format(name=filename)
        
        # 检查是否包含路径分隔符（完整路径）
        if "/" in filename or "\\" in filename:
            return self.style.get("backup_name_error5").format(name=filename)
        
        return False

    def check_duration(self, value):
        """
        检查duration参数是否合规

        Args:
            value: duration参数
        """

        # 正则匹配，例：1h、30d
        pattern = r'^\d+(\.\d)?[hsmdMw]$'
        
        # 进行匹配
        if not bool(re.match(pattern, str(value))):
            return self.style.get("duration_error1").format(duration=value)
        
        unit = value[-1]
        number = float(value[:-1])

        # 检查时间是否合法，比如不能有25h、0.5s
        if (unit == "m" or unit == "s") and (number < 1 or number > 60):
            return self.style.get("duration_error2")
        elif unit == "h" and (number < 1 or number > 720):
            return self.style.get("duration_error3")
        elif unit == "d" and (number < 1 or number > 30):
            return self.style.get("duration_error4")
        elif unit == "w" and (number < 1 or number > 4.28):
            return self.style.get("duration_error6")
        elif unit == "M" and number != 1:
            return self.style.get("duration_error5")
        return False
    
    def check_name(self, value):
        """
        检查是否能匹配QQ（昵称）的格式

        Args:
            value: 回复消息
        """

        pattern = r'^(\d+)（.+）$'
        match = re.match(pattern, value)
        if not bool(match):
            return True, self.style.get("qq_name_error").format(qq=value)
        elif len(match[1]) < 5 or len(match[1]) > 11:
            return True, self.style.get("qq_len_error").format(qq=match[1])
        else:
            return False, match[1]

    def check_target(self, value, id: str):
        """
        检查目标QQ是否合规以及是否在群内

        Args:
            value: target参数
            id: group_id群号
        """

        target = None

        # 用于检查是否需要增加备注
        ifname = True

        # 如果value是整数，则需要增加备注
        if value.isdigit():
            if len(value) < 5 or len(value) > 11:
                return True, self.style.get("qq_len_error").format(qq=value)
            target = value
            ifname = False

        # 如果不是，检查是否匹配QQ（昵称）的格式
        else:
            response, num = self.check_name(value)
            
            # 如果是，就return
            if response:
                return True, num
            target = num
            ifname = True

        # 如果需要添加备注，就检查是否在群里，如果不在就return
        if not ifname:
            group = id.split('（')[0]
            name, e = self.bot.get_group_member_nickname(group, target)
            if name is None:
                return True, e
            elif not name:
                retcode = e.get("retcode")
                # if retcode == 200 and e.get("wording") == "无法获取用户信息":
                if retcode == 200:
                    error_msg = self.style.get("get_nickname_error3").format(user_id=value,group_id=id)
                else:
                    error_msg = self.style.get("get_nickname_error").format(e=e.get("message"))
                return True, error_msg
            value = f'{value}（{name}）'
        return False, value
    
    def check_operator(self, value: str):
        
        operators = self.style.get("operator_list")
        operator = None

        # 用于检查是否需要增加备注
        ifname = True

        # 如果value是整数，则需要增加备注
        if value.isdigit():
            if len(value) < 5 or len(value) > 11:
                return True, self.style.get("qq_len_error").format(qq=value)
            operator = value
            ifname = False

        else:
            
            # 检查value是否作为昵称被写入了风格文件，是的话就return
            operator_nicknames = self.style.get("operator_nicknames_list")
            for key, operator in operator_nicknames.items():
                if value == key:
                    nickname = operators.get(operator, None)
                    if nickname is None:
                        return True, self.style.get("nickname_not_found").format(nickname=operator)
                    value = f'{operator}（{nickname}）'
                    return False, value
                
            # 如果不是，检查是否匹配QQ（昵称）的格式
            response, num = self.check_name(value)

            # 如果是，就return
            if response:
                return True, num
            operator = num
            ifname = True

        # 如果操作者在风格文件的管理员名单内，且ifname为False，则添加备注
        if int(operator) in operators:
            if not ifname:
                value = f'{value}（{operators.get(int(operator))}）'

        # 如果不在管理群名单，检查是否在管理群
        else:
            group = self.bot.config.get("QQgroup")
            operator_list = self.bot.get_group_member_list(group if group else "963462616")

            # 如果在，且ifname为False，则添加备注
            if operator in operator_list:
                if not ifname:
                    value = f'{value}（{operator_list.get(operator)}）' if operator_list.get(operator) else value

            # 如果都不在就return
            else:
                return True, self.style.get("edit_operator_error").format(group=f'{group}（{self.style.get("qq_groups").get(group)}）',operator=operator)
            
        return False, value

    def check_group_id(self, value: str):
        """
        检查group_id是否合规以及是否在风格文件的群列表中

        Args:
            value: group_id参数
        """

        # 检查value是否有2个及以上的字符
        if len(value) == 1:
            return True, self.style.get("qq_group_one_character").format(group=value)
        
        group = None
        
        # 用于检查是否需要增加备注
        ifname = True

        # 如果value是整数，则需要增加备注
        if value.isdigit():
            if len(value) < 5 or len(value) > 11:
                return True, self.style.get("qq_len_error").format(qq=value)
            group = value
            ifname = False

        # 如果不是，检查是否匹配QQ（昵称）的格式
        else:

            # 检查value是否作为昵称被写入了风格文件，是的话就return
            groups_nicknames = self.style.get("qq_groups_nicknames_list")
            for key, group_id in groups_nicknames.items():
                if value in key:
                    groups = self.style.get("qq_groups")
                    nickname = groups.get(group_id, None)
                    if nickname is None:
                        return True, self.style.get("nickname_not_found").format(nickname=group_id)
                    value = f'{group_id}（{nickname}）'
                    return False, value
                
            # 如果不是，检查是否匹配QQ（昵称）的格式
            response, num = self.check_name(value)
            
            # 如果都不是，就return
            if response:
                return True, num
            group = num
            ifname = True
        
        # 检查是否在风格文件的群列表中，如果不在就return
        groups = self.style.get("qq_groups")
        if int(group) not in groups:
            message = self.style.get("qq_group_not_found").format(group=group)
            message = f'{message}\n已知群列表：'
            for id, name in groups.items():
                message = f'{message}\n{id}：{name}'
            return True, message
        
        # 如果需要添加备注就自动添加
        if not ifname:
            value = f'{value}（{groups.get(int(group))}）'
        return False, value

    def handle_edit(self, command, images, operator):
        """
        修改日志的指定字段前检测value是否合法
        
        Args:
            command: 指令列表 = [
            log_id: 日志ID,
            field: 要修改的字段名,
            value: 新值,
            value2: duration参数，如果value不是禁言就没有
            ]
        """

        # 检查参数是否有3个，log_id是否是整数
        if len(command) == 3:
            return self.style.get("edit_command_len_error")
        log_id = command[2]
        if not log_id.isdigit():
            return self.style.get("log_id_error").format(id=log_id)
        
        field = command[3]
        value = None
        value2 = None

        # 查询log_id对应的log是否存在
        log = self.get_log_by_id_dict(log_id, False)
        if not log or log == {}:
            return self.style.get("details_none").format(id=log_id)
        
        # 检查mode是否在风格文件field_list被定义
        edit_list = self.style.get("field_list")
        if edit_list and field in edit_list:
            field = edit_list.get(field)
        else:
            return self.style.get("field_error").format(field=field)
        
        # 如果参数是3个，检查field是不是image，是的话删除log_id的老图片，并下载新的
        if len(command) == 4:
            if field == "image":
                if images == {}:
                    return self.style.get("no_image")
                e = self.delete_image(log_id)
                if e:
                    return e
                for i, url in images.items():
                    e = self.download_image(url, f'{log_id}_{i}')
                    if e:
                        return e
                return self.style.get("replace_image_success").format(id=log_id)
            else:
                return self.style.get("edit_command_len_error4")
        value = command[4]
        
        # 用于检查是否要额外修改duration，比如field=mode，value=禁言，value2=duration
        after_duration = False

        # 如果field是mode
        if field == "mode":

            # 检查是否是已知模式
            mode_list = self.style.get("mode_list")
            if value in mode_list:
                value = mode_list.get(value)
            else:
                return self.style.get("edit_mode_error").format(mode=value)
            
            # 如果value是禁言，检查参数是否为4个，检查第4个参数作为duration是否合规
            if value == "禁言":
                if len(command) == 6:
                    value2 = command[5]
                else:
                    return self.style.get("edit_command_len_error2")
                response = self.check_duration(value2)
                if response:
                    return response
                else:
                    after_duration = True

            # 如果value是其他模式，检查参数是否为3个
            else:
                if len(command) != 5:
                    return self.style.get("edit_command_len_error3")
                
                # 如果原来的模式是禁言，额外将duration设为None
                if log.get("mode") == "禁言":
                    after_duration = True
                    value2 = None
        else:
            # 检查参数是否为3个
            if len(command) != 5:
                return self.style.get("edit_command_len_error3")
            
            # 如果field是reason，检查reason是否不是纯数字
            if field == "reason":
                pattern = r'^[+-]?\d*\.?\d+$'
                if bool(re.match(pattern, value.strip())):
                    return self.style.get("reason_error").format(reason=value)
                
            # 如果field是operator，执行check_operator函数
            elif field == "operator":
                iftrue, value = self.check_operator(value)
                if iftrue:
                    return value

            # 如果field是duration，检查模式是不是禁言，duration不符合格式
            elif field == "duration":
                mode = log.get("mode")
                if mode != "禁言":
                    return self.style.get("modify_duration_error").format(id=log_id,mode=mode)
                response = self.check_duration(value)
                if response:
                    return response
                
            # 如果field是target，执行check_target函数
            elif field == "target":
                iftrue, value = self.check_target(value, log.get("group_id"))
                if iftrue:
                    return value
                
            # 如果field是group_id，执行check_group_id函数
            elif field == "group_id":
                iftrue, value = self.check_group_id(value)
                if iftrue:
                    return value
            
            # 如果field是time，检查时间合不合法
            elif field == "time":
                value = value.replace(",", " ")
                response = self.validate_time_with_detail(value)
                if response:
                    return response
                
            elif field == "id":
                if not value.isdigit():
                    return self.style.get("log_id_error").format(id=log_id)
                return self.safe_change_log_id(log_id, value)

            # 如果field不匹配，说明风格文件内的value不正确，return
            else:
                return self.style.get("field_error2").format(field=field)
        
        old = log.get(field)
        if old == value:
            return self.style.get("modify_error").format(field=field,id=log_id,old=old)
        self.modify(log_id, field, value)

        if after_duration:
            self.modify(log_id, "duration", value2)

        # 更新成功后将操作者存入缓存，提醒网页端有人在5分钟内编辑过
        self.cache[log_id] = operator

        return self.style.get("modify_success").format(field=field,new=value,id=log_id,old=old)

    def modify(self, log_id, field, value):
        """修改日志指定字段"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            # 使用参数化查询防止SQL注入
            query = f"UPDATE logs SET {field} = ? WHERE id = ?"
            cursor.execute(query, (value, log_id))
            conn.commit()

    def safe_change_log_id(self, old_id, new_id):
        """安全修改日志ID - 使用UPDATE直接修改"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            try:
                # 1. 开始事务
                cursor.execute("BEGIN TRANSACTION")
                
                # 2. 检查新旧ID
                cursor.execute("SELECT COUNT(*) FROM logs WHERE id = ?", (old_id,))
                if cursor.fetchone()[0] == 0:
                    return self.style.get("modify_id_not_found").format(id=old_id)
                
                cursor.execute("SELECT COUNT(*) FROM logs WHERE id = ?", (new_id,))
                if cursor.fetchone()[0] > 0:
                    return self.style.get("modify_id_present").format(id=new_id)
                
                # 3. 直接更新ID
                cursor.execute("UPDATE logs SET id = ? WHERE id = ?", (new_id, old_id))
                
                # 4. 重命名关联文件
                response = self.rename_log_files(old_id, new_id)
                if response:
                    cursor.execute("ROLLBACK")
                    return response
                
                # 5. 检查是否需要刷新自增计数器
                cursor.execute("SELECT MAX(id) FROM logs")
                max_id = cursor.fetchone()[0] or 0
                
                # 只有当删除的是最大ID时才需要更新
                if int(old_id) > max_id:
                    cursor.execute("""
                        UPDATE sqlite_sequence 
                        SET seq = ? 
                        WHERE name = 'logs'
                    """, (max_id,))
                
                conn.commit()
                
                # 可选：清理WAL文件
                cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")

                
                return self.style.get("modify_id_success").format(old_id=old_id, new_id=new_id)
                
            except sqlite3.Error as e:
                # 回滚事务
                cursor.execute("ROLLBACK")
                return self.style.get("modify_id_error").format(e=str(e))
            
    def rename_log_files(self, old_id, new_id):
        """重命名日志关联的文件"""
        renamed_count = 0
        
        # 重命名图片文件
        pattern = os.path.join(self.image, f'{old_id}_*')
        for old_path in glob.glob(pattern):
            # 获取文件名部分
            filename = os.path.basename(old_path)
            
            # 替换ID部分
            # old_id_xxx.jpg -> new_id_xxx.jpg
            if filename.startswith(f"{old_id}_"):
                new_filename = filename.replace(f"{old_id}_", f"{new_id}_", 1)
                new_path = os.path.join(self.image, new_filename)
                
                try:
                    os.rename(old_path, new_path)
                    print(f"📁 重命名文件: {filename} → {new_filename}")
                    renamed_count += 1
                except Exception as e:
                    print(f"❌ 重命名失败 {filename}: {str(e)}")
                    return self.style.get("rename_image_error").format(filename=filename,e=str(e))
        
        return False

    def _extract_cq_image(self, text: str, mode: int = 1):
        """
        提取CQ图片码并分离文本
        
        Args:
            text: 包含CQ码的原始文本
            
        Returns:
            tuple: (清理后的文本, 提取出的CQ图片码列表)
        """

        # 使用正则表达式查找所有[CQ:image...]内容
        if mode == 1:
            pattern = r'(\[CQ:image[^\]]*\])'
        else:
            pattern = r'(\[CQ:[^\]]*\])'
        
        # 替换掉所有CQ图片码
        cleaned_text = re.sub(pattern, '', text)
        
        # 清理多余的空格（可选）
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        
        return cleaned_text
    
    def handle_mode(self, match: list, images: dict, operator: int):
        """
        检测参数是否合法
        
        Args:
            match: 按空格分隔好的消息列表
            images: 图片url列表
            operator: 操作者
            
        Returns:
            response: 处理好的log字典
        """

        # 创建log字典
        response = {}
        mode = match[1]
        items = len(match)

        # 检查参数数量是否达标，如果模式是禁言，检查是否有duration参数
        if mode == "禁言":
            if items == 6:
                duration = match[5]
                value = self.check_duration(duration)

                if not value:
                    response["duration"] = duration
                else:
                    return value
            else:
                return self.style.get("log_command_len_error2")
        else:
            if items != 5:
                return self.style.get("log_command_len_error1")
        

        # 没有图片就return
        if images == {}:
            return self.style.get("no_image")
        
        response["mode"] = mode
        
        group_id = match[4]
        if_group_id, group_id = self.check_group_id(group_id)
        if if_group_id:
            return group_id
        response["group_id"] = group_id
        
        target = match[2]
        if_target, target = self.check_target(target, group_id)
        if if_target:
            return target
        response["target"] = target
            
        reason = match[3]
        pattern = r'^[+-]?\d*\.?\d+$'
        if reason and not bool(re.match(pattern, reason.strip())):
            response["reason"] = match[3]
        else:
            return self.style.get("reason_error").format(reason=reason)
        
        if_operator, operator = self.check_operator(str(operator))
        if if_operator:
            return operator
        response["operator"] = operator

        return response

    def handle_search(self, match, mode):
        """
        检测参数是否合法
        
        Args:
            match: 按空格分隔好的消息列表
            mode: 消息模式
            
        Returns:
            message: 回复消息
        """

        field = None
        value = None
        search_mode = 1
        limit = None

        # 消息模式是1，代表是/log <QQ号>搜索
        if mode == 1:
            value = match[1]
            if len(value) < 5 or len(value) > 11:
                return self.style.get("qq_len_error").format(qq=value)
            field = "target"
            if len(match) == 3:
                limit = match[2]
                if not limit.isdigit():
                    return self.style.get("limit_error").format(limit=limit)
            value = value.split('（')[0]
        
        # 消息模式是2，代表是/log search <参数> <内容>搜索
        else:

            # 检查是否有limit参数，以及是否合规
            if len(match) == 5:
                limit = match[4]
                if not limit.isdigit():
                    return self.style.get("limit_error").format(limit=limit)
            
            field = match[2]
            value = match[3]

            # 检查mode是否在风格文件field_list被定义
            edit_list = self.style.get("field_list")
            if edit_list and field in edit_list:
                field = edit_list.get(field)
            else:
                return self.style.get("field_error").format(field=field)
            
            # 如果field是mode
            if field == "mode":

                # 检查是否是已知模式
                mode_list = self.style.get("mode_list")
                if value in mode_list:
                    value = mode_list.get(value)
                else:
                    return self.style.get("edit_mode_error").format(mode=value)
                search_mode = 3
                
            # 如果field是reason，检查reason是否不是纯数字
            elif field == "reason":
                pattern = r'^[+-]?\d*\.?\d+$'
                if bool(re.match(pattern, value.strip())):
                    return self.style.get("reason_error").format(reason=value)
                search_mode = 2
                
            # 如果field是operator
            elif field == "operator":
                iftrue, value = self.check_operator(value)
                if iftrue:
                    return value
                value = value.split('（')[0]

            # 如果field是duration，检查模式是不是禁言，duration不符合格式
            elif field == "duration":
                response = self.check_duration(value)
                if response:
                    return response
                search_mode = 3
                
            # 如果field是target，检查是昵称还是整数
            elif field == "target":
                value = value.split('（')[0]

                if not value.isdigit():
                    search_mode = 2

                elif len(value) < 5 or len(value) > 11:
                    return self.style.get("qq_len_error").format(qq=value)
                
            # 如果field是group_id，执行check_group_id函数
            elif field == "group_id":
                iftrue, value = self.check_group_id(value)
                if iftrue:
                    return value
                value = value.split('（')[0]
            
            # 如果field是time，检查时间合不合法
            elif field == "time":
                value = value.replace(",", " ")
                search_mode = 2
                
            elif field == "id":
                return self.handle_detail(value)
            
            elif field == "image":
                return self.style.get("field_not_support").format(field=field)

            # 如果field不匹配，说明风格文件内的value不正确，return
            else:
                return self.style.get("field_error2").format(field=field)
            
        log_search_limit = limit if limit else self.style.get("log_search_limit")

        # 查询该字段的log
        logs = self.query_logs(field, value, search_mode, log_search_limit)
        if logs == []:
            return self.style.get(f"value_not_found{search_mode}").format(field=field,value=value)
        
        # 如果查询的是target，增加风险值
        if field == "target":
            count, risk, _ = self.get_log_count_by_qq("target", value, mode=search_mode)
            ifqq = self.style.get("log_search_qq").format(risk=risk)
        else:
            count, _, _ = self.get_log_count_by_qq(field, value, iftotal=False, mode=search_mode)
            ifqq = ""
        message = self.style.get(f"log_search{search_mode}").format(field=field,value=value,log_search_limit=log_search_limit,l=count,ifqq=ifqq)

        # 遍历log列表，生成回复
        for log in logs:
            message = f'{message}\n{self.style.get("log_search_value").format(id=log["id"],time=log["time"],target=log["target"],mode=log["mode"],operator=log["operator"],group_id=log["group_id"],reason=log["reason"],duration=log["duration"] or self.style.get("no_duration", "不适用"),c=log["image_count"])}'
        
        return message
    
    def handle_detail(self, id):
        """
        检查第id是否是整数，获取log信息以及图片地址，生成回复
        
        Args:
            id: log_id
            
        Returns:
            message: 回复消息
        """

        if id.isdigit():
            get_log = self.get_log_by_id_dict(id)
            if get_log is None:
                return self.style.get("details_none").format(id=id)
            images_paths = get_log["images_path"]
            message = self.style.get("log_details").format(id=id,time=get_log["time"],mode=get_log["mode"],operator=get_log["operator"],group_id=get_log["group_id"],target=get_log["target"],reason=get_log["reason"],duration=get_log["duration"] or self.style.get("no_duration", "不适用"),c=get_log["image_count"])
            for path in sorted(images_paths.keys()):
                cq_image = f"[CQ:image,file=file:///{images_paths[path]}]"
                message = f"{message}\n{cq_image}"
            return message
        else:
            return self.style.get("log_id_error").format(id=id)
        
    def handle_help(self, match):
        """
        处理help回复
        
        Args:
            match: 按空格分隔好的消息列表
            
        Returns:
            message: 回复消息
        """

        # 没有输入参数返回概括版log系统帮助信息，参数超过2个返回如何使用/log help的帮助信息
        items = len(match)
        if items == 2:
            return self.style.get("help")
        elif items > 4:
            return self.style.get("help_list", {}).get("action", {}).get("help")
        help_list = self.style.get("help_list")

        # help是第一个参数作为昵称对应的正式参数名，message是假设只有一个参数时的回复，iflist是否需要遍历help对应字典
        help, message, iflist = self.get_value_by_nickname(match, help_list)
        if help is None:
            return message
        
        # 如果有第二个参数
        if items > 3:

            # 获取第一个参数对应在help_list表层的字典
            help_list = help_list.get(help, None)
            if help_list is None:
                return self.style.get("help_error2").format(action=help)
            help2 = match[3]

            # 获取第一个参数对应的昵称字典
            nickname_list = self.style.get(f"{help}_list", None)
            if nickname_list is None:
                return self.style.get("help_error3").format(action=help)
            
            # 获取第二个参数在昵称字典中的正式参数名
            help_official = nickname_list.get(help2, None)
            if help_official is None:
                return self.style.get("help_error4").format(action=help)
            
            # 如果第一个参数在help_list表层对应的不是字典（管理员和QQ群昵称列表）返回第二个参数和对应的QQ号
            if type(help_list) == str:
                return f'{help2}：{help}'
            
            # 获取第二个参数的正式参数名在第一个参数对应的help_list字典中的帮助信息
            message = help_list.get(help_official, None)
            if message is None:
                return self.style.get("help_error5").format(action=help)
            
        else:
            # 遍历昵称列表
            if iflist:
                _list = self.style.get(f'{help}_list')
                message = self.format_dict_message(message, _list)
        return message
    
    def format_dict_message(self, message: str, data: dict, indent: int = 0) -> str:
        """
        格式化字典为消息字符串
        
        Args:
            message: 初始消息
            data: 要遍历的字典（可以是嵌套字典）
            indent: 缩进级别（用于递归时控制格式）
        
        Returns:
            格式化后的消息字符串
        """
        
        indent_space = " " * indent * 2  # 每级缩进2个空格
        
        for key, value in data.items():
            if isinstance(value, dict):
                # 如果是字典，递归处理
                message = f'{message}\n{indent_space}{key}：'
                message = self.format_dict_message(message, value, indent + 1)
            elif isinstance(value, list):
                # 如果是列表，遍历列表项
                message = f'{message}\n{indent_space}{key}：'
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        message = f'{message}\n{indent_space}  [{i}]'
                        message = self.format_dict_message(message, item, indent + 2)
                    else:
                        message = f'{message}\n{indent_space}  [{i}]：{item}'
            else:
                # 基本类型直接输出
                message = f'{message}\n{indent_space}{key}：{value}'
        
        return message

    def get_value_by_nickname(self, match, help_list):
        """
        获取第一个参数对应的正式参数名
        
        Args:
            match: 按空格分隔好的消息列表
            help_list: 风格文件中的help_list
            
        Returns:
            help: 正式参数名
            message: 回复消息
            iflist: 是否需要遍历昵称列表
        """

        help = match[2]
        field_list = self.style.get("field_list")
        help_list_list = self.style.get("help_list_list")
        backup_list = self.style.get("backup_list")
        action_list = self.style.get("action_list")
        mode_list = self.style.get("mode_list")
        style_list = self.style.get("style_list")
        iflist = False
        if help in help_list_list:
            iflist = True
            help = help_list_list[help]
            message = help_list.get(help)
            if type(message) == dict:
                message = message.get(help)
            return help, message, iflist
        elif help in field_list:
            help = field_list[help]
            return help, help_list.get("field").get(help), iflist
        elif help in action_list:
            help = action_list[help]
            return help, help_list.get("action").get(help), iflist
        elif help in mode_list:
            help = mode_list[help]
            return help, help_list.get("mode").get(help), iflist
        elif help in backup_list:
            help = backup_list[help]
            return help, help_list.get("backup").get(help), iflist
        elif help in style_list:
            help = style_list[help]
            return help, help_list.get("style").get(help), iflist
        else:
            return None, self.style.get("help_error").format(action=help), iflist

    def handle_backup(self, match):
        """
        处理backup回复
        
        Args:
            match: 按空格分隔好的消息列表
            
        Returns:
            message: 回复消息
        """

        items = len(match)
        action = match[1]
        backups = self.get_backup_files_sorted()
        ifall = False

        if items == 2:
            ifall = True
        else:

            # 输入超过2个参数，返回帮助信息
            if items > 4:
                return self.style.get("help_list").get("action").get(action)
            field = match[2]
            backup_list = self.style.get("backup_list")

            # 第一个参数不在昵称字典中就return
            if field in backup_list:
                field = backup_list[field]
            else:
                return self.style.get("backup_field_error").format(field=field)
            
            # 如果field是make，检查名字是否合法，执行备份函数
            if field == "make":
                name = None
                if items > 3:
                    name = ' '.join(match[3:])
                    iflegal = self.check_filename(name)
                    if iflegal:
                        return iflegal
                return self.backup_without_locks(name)
            
            # 如果是delete，检查参数数量，id是否合法，执行删除函数
            elif field == "delete":
                if items != 4:
                    return self.style.get("backup_id_not_found")
                id = match[3]
                if (not id.isdigit()) or int(id) > len(backups) or int(id) < 1:
                    return self.style.get("backup_id_not_found")
                path = os.path.join(self.backup, backups[int(id)-1])
                return self.delete_file(path)
            
            # 如果是back，检查参数数量，id是否合法，执行备份函数
            elif field == "back":
                if items != 4:
                    return self.style.get("backup_id_not_found")
                id = match[3]
                if (not id.isdigit()) or int(id) > len(backups) or int(id) < 1:
                    return self.style.get("backup_id_not_found")
                path = backups[int(id)-1]
                return self.extract_zip(path)
            
            # 如果是back，检查第二个参数是否是 开/关，执行开关函数
            elif field == "auto":
                if items == 3:
                    auto = self.style.get("backup_auto_list").get("开") if self.backup_running else self.style.get("backup_auto_list").get("关")
                    return self.style.get("backup_auto").format(auto=auto)
                auto = match[3]
                state = self.style.get("backup_auto_list").get(auto, None)
                if state == "开":
                    return self.start_backup_scheduler()
                elif state == "关":
                    return self.stop_backup_scheduler()
                else:
                    return self.style.get("backup_auto_error").format(auto=auto)
            
            elif field == "list":
                ifall = False
            
            else:
                return self.style.get("backup_error").format(action=field)
        
        # 没有输入参数或参数为list，返回备份信息
        blist = ""
        for i, value in enumerate(backups):
            blist = f'{blist}\n{i+1}、{value}'
        blist = self.style.get("backup_details2").format(list=blist)
        if ifall:
            auto = self.style.get("backup_auto_list").get("开") if self.backup_running else self.style.get("backup_auto_list").get("关")
            delay = self.bot.config.get("backup_delay")
            limit = self.bot.config.get("backup_limit")
            last = self.bot.config.get("backup_time")
            message = f"{self.style.get("backup_details").format(auto=auto,delay=delay,limit=limit,last=last)}\n{blist}"
        else:
            message = blist
        return message

    def handle_style(self, match, items):
        """
        处理style回复
        
        Args:
            match: 按空格分隔好的消息列表
            items: match的数量
            
        Returns:
            message: 回复消息
        """

        # 没有输入参数，返回当前风格
        if items == 2:
            return self.style.get("style_now").format(style=self.style_name)
        field = match[2]
        style_list = self.style.get("style_list")
        help_list = self.style.get("help_list").get("style")

        # 第一个参数不在昵称字典中就return
        if field in style_list:
            field = style_list[field]
        else:
            return self.style.get("style_field_error").format(field=field)
        styles = self.get_backup_files_sorted(self.styles)
        
        # 如果field是list，获取风格列表
        if field == "list":
            if items > 3:
                return help_list.get(field)
            message = self.style.get("style_details")
            for i, value in enumerate(styles):
                message = f"{message}\n{i+1}、{value}"
            return message
        
        # 如果field是load，检查第二个参数是编号还是名字，执行加载函数
        elif field == "load":
            if items != 4:
                return help_list.get(field)
            name = match[3]
            if name.isdigit() and int(name) <= len(styles) and int(name) > 0:
                name = styles[int(name)-1]
            name, _ = os.path.splitext(name)
            style = self.read_config(name)
            if style is not None:
                self.style = style
                return self.style.get("style_success").format(name=name)
            else:
                e = self.nostyle
                self.nostyle = False
                return e
            
        # 如果field是reload，执行重载函数
        elif field == "reload":
            if items > 3:
                return help_list.get(field)
            style = self.read_config(self.style_name)
            if style is not None:
                self.style = style
                return self.style.get("style_success").format(name=self.style_name)
            else:
                e = self.nostyle
                self.nostyle = False
                return e
            
        # 如果field是delete，检查第二个参数是编号还是名字，执行删除函数
        elif field == "delete":
            if items != 4:
                return help_list.get(field)
            name = match[3]
            if name.isdigit() and int(name) <= len(styles) and int(name) > 0:
                name = styles[int(name)-1]
            name, _ = os.path.splitext(name)
            path = os.path.join(self.styles, f"{name}.yml")
            return self.delete_file(path)
        
        else:
            return self.style.get("style_error").format(action=field)
        
    def handle_execute(self, match):
        """
        处理execute回复
        
        Args:
            match: 按空格分隔好的消息列表
            
        Returns:
            message: 回复消息
        """

        # 检查log_id是否是整数，该log是否存在
        id = match[2]
        if not id.isdigit():
            return self.style.get("log_id_error").format(id=id)
        log = self.get_log_by_id_dict(id, False)
        if log is None:
            return self.style.get("details_none").format(id=id)
        mode = log.get("mode")
        group = int(log.get("group_id").split('（')[0])
        target = int(log.get("target").split('（')[0])

        operators = self.style.get("operator_list")
        former_operators = self.style.get("former_operator_list")
        if mode in ["禁言","踢出","拉黑"] and target in operators and target not in former_operators:
            return self.style.get("execute_error2").format(mode=mode)

        # 根据模式执行相应的函数
        if mode == "禁言":
            duration = log.get("duration")
            return self.bot.mute_member(group, target, duration)
        elif mode == "踢出":
            groups = self.style.get("qq_groups")
            message = self.bot.kick_member(group, target)
            for other_group in groups:
                if other_group != group:
                    message = f"{message}\n{self.bot.kick_member(f"{other_group}（{groups[other_group]}）", target)}"
            return message
        elif mode == "拉黑":
            groups = self.style.get("qq_groups")
            message = self.bot.kick_member(group, target, True)
            for other_group in groups:
                if other_group != group:
                    message = f"{message}\n{self.bot.kick_member(f"{other_group}（{groups[other_group]}）", target, True)}"
            return message
        else:
            return self.style.get("execute_field_error").format(mode=mode)

    def process_command(self, command: str, images: dict, operator: int) -> str:
        """
        处理qq消息
        
        Args:
            command: 原始消息列表
            images: 图片url列表
            operator: 操作者
            
        Returns:
            message: 需要发送的回复
        """

        # 如果没有加载风格文件就return
        if self.nostyle:
            return self.nostyle
        
        # 删除图片CQ码
        commands = self._extract_cq_image(command)

        # 按空格分隔消息
        match = commands.split()
        
        items = len(match)

        # 如果只有关键词，就return help信息
        if items == 1:
            return self.style.get("help")
        
        else:
            # 第一个参数设为actoin
            action = match[1]

            # 如果第一个参数是纯数字，检查是否只有一个参数
            if action.isdigit():
                if items > 3:
                    return self.style.get("log_search_error")
                return self.handle_search(match, 1)
            
            # 检查action是否在风格文件action_list被定义
            action_list = self.style.get("action_list")
            mode_list = self.style.get("mode_list")
            if action_list and action in action_list:
                action = action_list.get(action)
                
            # 如果action在风格文件的mode_list中，执行参数处理函数
            elif mode_list and action in mode_list:
                action = mode_list[action]
                if items < 3:
                    return self.style.get("help_list").get("mode").get(action)
                
                response = self.handle_mode(match, images, operator)

                # 如果返回值是报错信息就return，否则添加log
                if type(response) == str:
                    return response
                log_id = self.add_log(response)

                # 下载图片并命名
                e = self.delete_image(log_id)
                if e:
                    return e
                for i, url in images.items():
                    e = self.download_image(url, f'{log_id}_{i}')
                    if e:
                        return e
                
                # 查询该qq的log数量并生成回复消息
                target = match[2].split('（')[0]
                count, risk, _ = self.get_log_count_by_qq("target", target)
                return self.style.get("add_log_success").format(id=log_id,l=count,c=str(len(images)),risk=risk)
            else:
                return self.style.get("action_error").format(action=action)

            # 如果action是help，执行信息处理函数
            if action == "help":
                return self.handle_help(match)
            
            # 如果action是style，执行信息处理函数
            elif action == "style":
                return self.handle_style(match, items)
                
            # 如果action是delete，检查第二个参数是否是整数，尝试删除
            elif action == "delete":
                if items < 3:
                    return self.style.get("help_list").get("action").get(action)
                n = 2
                message = ""
                for i in range(items - 2):
                    log_id = match[n]
                    if log_id.isdigit():
                        _, response = self.delete_log(log_id)
                        message = f"{message}\n{response}"
                    else:
                        message = f"{message}\n{self.style.get("log_id_error").format(id=log_id)}"
                    n += 1
                return message

            # 如果action是detail，执行信息处理函数
            elif action == "detail":
                if items != 3:
                    return self.style.get("help_list").get("action").get(action)
                id = match[2]
                return self.handle_detail(id)
                
            # 如果action是edit，执行参数检查的函数
            elif action == "edit":
                if items < 3:
                    return self.style.get("help_list").get("action").get(action)
                return self.handle_edit(match, images, operator)
            
            # 如果action是search，执行参数检查的函数
            elif action == "search":
                if items < 4 or items > 5:
                    return self.style.get("help_list").get("action").get(action)
                return self.handle_search(match, 2)
            
            # 如果action是backup，执行参数检查的函数
            elif action == "backup":
                # 检查是否正在进行自动备份
                if self.now_backup:
                    return self.style.get("backup_running")
                self.now_backup = True
                message = self.handle_backup(match)
                self.now_backup = False
                return message

            # 如果action是execute，执行参数检查的函数
            elif action == "execute":
                if items != 3:
                    return self.style.get("help_list").get("action").get(action)
                return self.handle_execute(match)

            # 如果action是get，检查是否输入第二个参数，第二个参数是否是整数
            elif action == "get":
                if items > 3:
                    return self.style.get("help_list").get("action").get(action)
                elif items == 2:
                    number = 1
                else:
                    number = match[2]
                    pattern = r'^[+-]?\d+$'
                    if bool(re.match(pattern, number)):
                        number = int(number)
                    else:
                        return self.style.get("get_error").format(n=number)
                    
                # 获取第n个参数
                id = self.get_nth_id(number)
                if type(id) == str:
                    return id
                else:
                    return self.handle_detail(str(id))

            # action在action_list的key但是value错误
            else:
                return self.style.get("action_error2").format(action=action)
    
    def get_log_count_by_qq(self, field, target: str, ifcount: bool = True, iftotal: bool = True, ifstate: bool = False, mode: int = 1):
        """根据字段查询记录数量"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            # 查询所有相关记录
            if mode == 1:
                sql = "LIKE ? || '%'"
            elif mode == 2:
                sql = "LIKE '%' || ? || '%'"
            else:
                sql = "= ?"
            sql = f"SELECT mode FROM logs WHERE {field} {sql} ORDER BY time ASC"
            cursor.execute(sql, (str(target),))
            records = cursor.fetchall()
            count = len(records) if ifcount else None
            
            # 计算加权次数
            total_weight = 0
            weight = 0
            state = "存活"
            if (iftotal or ifstate) and field == "target":
                risk = self.style.get("risk_value_list")
                for i, record in enumerate(records):
                    mode = record[0]

                    # 查看风格文件中的risk_value_list有没有设定该次违规的的加权值
                    if iftotal and mode in risk:
                        if (i+1) in risk[mode]:
                            weight = risk[mode][i+1]
                        else:
                            weight = risk[mode]["normal"]
                        total_weight += weight

                    if ifstate :
                        if mode == "踢出" and state == "存活":
                            state = f"已{mode}"
                        elif mode == "拉黑" and (state == "存活" or state == "已踢出"):
                            state = f"已{mode}"
            
            return count, total_weight, state

    async def async_get_log_count_by_qq(self, conn, field, target: str, ifcount: bool = True, iftotal: bool = True, ifstate: bool = False, mode: int = 1):
        """根据字段查询记录数量"""
        if mode == 1:
            sql = "LIKE ? || '%'"
        elif mode == 2:
            sql = "LIKE '%' || ? || '%'"
        else:
            sql = "= ?"
        sql = f"SELECT mode FROM logs WHERE {field} {sql} ORDER BY time ASC"
        records = await conn.execute_fetchall(sql, (str(target),))
        count = len(records) if ifcount else None
        
        # 计算加权次数
        total_weight = 0
        weight = 0
        state = "存活"
        if (iftotal or ifstate) and field == "target":
            risk = self.style.get("risk_value_list")
            for i, record in enumerate(records):
                mode = record[0]
                if iftotal and mode in risk:
                    if (i+1) in risk[mode]:
                        weight = risk[mode][i+1]
                    else:
                        weight = risk[mode]["normal"]
                    total_weight += weight
                if ifstate :
                    if mode == "拉黑":
                        state = f"已{mode}"
                        break
                    elif mode == "踢出":
                        state = f"已{mode}"
        
        return count, total_weight, state
        
    def get_log_by_id_dict(self, log_id, ifimage: bool = True):
        """根据ID查找日志，返回字典格式"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row  # 让返回结果为 Row 对象
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM logs WHERE id = ?", (log_id,))
            row = cursor.fetchone()
            
            if row:
                row = dict(row)
                if ifimage:
                    row['images_path'] = self.get_images_paths(log_id)
                    row["image_count"] = str(len(row['images_path']))
                return row
            return None
        
    async def get_total_logs_count(self) -> int:
        """获取日志总数"""
        async with aiosqlite.connect(self.db_name) as conn:
            row = await conn.execute_fetchall('SELECT COUNT(*) FROM logs')
            return row[0][0] or 0
    
    async def get_all_logs(self, limit: int = 100, offset: int = 0, url: str = "images/logs") -> List[Dict]:
        """
        获取所有日志（发送数据给前端）
        :param limit: 返回的最大记录数
        :return: 所有日志记录
        """
        async with aiosqlite.connect(self.db_name) as conn:
            conn.row_factory = aiosqlite.Row
            rows = await conn.execute_fetchall('''
                SELECT id, target, mode, reason, group_id, duration, operator, time
                FROM logs
                ORDER BY id DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset))

            logs = []
            need_risk = set()
            for row in rows:
                images_path = await asyncio.to_thread(self.get_images_paths, row['id'], url)
                row = dict(row)
                # row["image_count"] = str(len(images_path))
                row["images_path"] = images_path
                logs.append(row)
                need_risk.add(str(row['target']).split('（')[0])
            others = {}
            for i in need_risk:
                others[i] = {}
                others[i]["count"], others[i]["risk"], others[i]["state"] = await self.async_get_log_count_by_qq(conn, "target", i, True, True, True)
            return logs, others
        
    def get_nth_id(self, n: int) -> int:
        """
        获取按id降序排列的第n个记录的id
        
        Args:
            n: 位置索引，正数表示从大到小第几个，负数表示从小到大第几个
        
        Returns:
            id: 找到的id，如果不存在则返回None
        """
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            order = ""
            
            if n > 0:
                # 正数：从大到小第n个
                cursor.execute('''
                    SELECT id FROM logs 
                    ORDER BY id DESC 
                    LIMIT 1 OFFSET ?
                ''', (n - 1,))
                order = self.style.get("order_forward")
            elif n < 0:
                # 负数：从小到大第n个（倒数第|n|个）
                cursor.execute('''
                    SELECT id FROM logs 
                    ORDER BY id ASC 
                    LIMIT 1 OFFSET ?
                ''', (abs(n) - 1,))
                order = self.style.get("order_reverse")
            else:
                # n=0，通常返回第一个或最后一个，这里返回最大id（第1个）
                cursor.execute('SELECT id FROM logs ORDER BY id DESC LIMIT 1')
                order = self.style.get("order_forward")
            
            result = cursor.fetchone()
            return result[0] if result else self.style.get("get_error").format(order=order,n=n)
    
    def add_log(self, logs: dict) -> int:
        """
        添加日志记录
        :return: 插入记录的ID
        """
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO logs (mode, target, reason, duration, operator, group_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (logs["mode"], logs["target"], logs["reason"], logs.get("duration", None), logs.get("operator"), logs.get("group_id")))
            conn.commit()
            return cursor.lastrowid
        
    def add_log2(self, mode, target, reason, duration, operator, group_id, time) -> int:
        """
        用于迁移xt数据库
        :return: 插入记录的ID
        """
        
        operators = self.style.get("operator_list")

        # 如果操作者在风格文件的管理员名单内，且ifname为False，则添加备注
        if int(operator) in operators:
                operator = f'{operator}（{operators.get(int(operator))}）'

        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO logs (mode, target, reason, duration, operator, group_id, time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (mode, target, reason, duration, operator, group_id, time))
            conn.commit()
            return cursor.lastrowid
        
    def get_images_paths(self, id: str, url: int = None) -> dict:
        pattern = os.path.join(self.image, f"{id}_*")
        file_paths = glob.glob(pattern)
        images_path = {}
        for file_path in file_paths:
            filename = os.path.basename(file_path)
            name_without_ext = os.path.splitext(filename)[0]
            star_part = name_without_ext.split('_', 1)[1]
            if url is None:
                images_path[int(star_part)] = os.path.abspath(file_path)
                print(images_path[int(star_part)])
            elif not url:
                images_path[int(star_part)] = f"https://curator.ip-ddns.com:8000/api/files/images/logs/{os.path.basename(file_path)}"
                # images_path[int(star_part)] = file_path
            else:
                images_path[int(star_part)] = os.path.join(url, filename)
        return images_path
    
    def query_logs(self, field: str, value: str, mode: int, limit: int = 10) -> List[Dict]:
        """
        查询指定字段的日志
        :param field: 字段名字
        :param value: 字段内容
        :param limit: 返回的最大记录数
        :return: 日志记录列表
        """

        # 查找模式1是匹配开头为value的，2是匹配中间包含value的，3是完全匹配value的
        sql = None
        if mode == 1:
            sql = "LIKE ? || '%'"
        elif mode == 2:
            sql = "LIKE '%' || ? || '%'"
        else:
            sql = "= ?"

        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(f'''
                SELECT id, mode, target, reason, operator, duration, time, group_id
                FROM logs
                WHERE {field} {sql}
                ORDER BY id DESC
                LIMIT ?
            ''', (value, limit))
            
            logs = []
            a = cursor.fetchall()
            for row in a:
                images_path = self.get_images_paths(row['id'])
                row = dict(row)
                row["image_count"] = str(len(images_path))
                row["images_path"] = images_path
                logs.append(row)
            return logs
    
    def delete_image(self, log_id: str):
        """
        删除指定ID日志的图片
        :param log_id: 日志ID
        :return: 回复的消息
        """
        
        deleted_count = 0
        # 遍历文件夹中的所有文件
        for filename in os.listdir(self.image):
            # 检查是否以 id_ 开头
            if filename.startswith(f"{log_id}_"):
                file_path = os.path.join(self.image, filename)
                
                try:
                    os.remove(file_path)
                    print(f"✅ 已删除: {filename}")
                    deleted_count += 1
                except Exception as e:
                    print(f"❌ 删除失败 {filename}: {str(e)}")
                    return self.style.get("delete_image_error").format(e=str(e))
        print(f"已删除{deleted_count}张图片")
        return False

    def delete_log(self, log_id: int) -> str:
        """
        删除指定ID的日志
        :param log_id: 日志ID
        :return: 回复的消息
        """
        log_id = int(log_id)
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                
                # 1. 检查log_id是否存在
                cursor.execute("SELECT 1 FROM logs WHERE id = ?", (log_id,))
                if cursor.fetchone() is None:
                    return True, self.style.get("details_none").format(id=log_id)
                
                # 2. 删除对应id的图片（在数据库事务之前）
                ifdelete = self.delete_image(log_id)
                if ifdelete:
                    return True, ifdelete
                
                # 3. 删除数据库记录
                cursor.execute('DELETE FROM logs WHERE id = ?', (log_id,))
                
                # 4. 检查是否需要刷新自增计数器
                cursor.execute("SELECT MAX(id) FROM logs")
                max_id = cursor.fetchone()[0] or 0
                
                # 只有当删除的是最大ID时才需要更新
                if log_id > max_id:
                    cursor.execute("""
                        UPDATE sqlite_sequence 
                        SET seq = ? 
                        WHERE name = 'logs'
                    """, (max_id,))
                
                conn.commit()
                
                # 可选：清理WAL文件
                cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                
                return False, self.style.get("delete_log_success").format(id=log_id)
                
        except sqlite3.Error as e:
            # 如果发生锁错误，可以重试
            if "locked" in str(e):
                return True, "数据库正忙，请稍后再试"
            raise

    # def update_record_to_demerit(self):
    #     """将所有mode为'记录'的记录改为'记过'"""
    #     with sqlite3.connect(self.db_name) as conn:
    #         cursor = conn.cursor()
    #         cursor.execute(
    #             "UPDATE logs SET mode = '记过' WHERE mode = '记录'"
    #         )
    #         affected_rows = cursor.rowcount
    #         conn.commit()
    #         return affected_rows
    
    def __del__(self):
        """析构函数，确保线程正确停止"""
        self.stop_backup_scheduler()

# 使用示例
if __name__ == "__main__":
    # 创建日志系统实例
    log_system = LogSystem()
    command7 = input()
    result7 = log_system.process_command(command7)
    print(result7)