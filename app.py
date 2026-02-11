# from flask import *
import threading, time, os, secrets, aiofiles.os, sqlite3
from logs import LogSystem
from werkzeug.utils import safe_join
import uvicorn
from quart import Quart, render_template, redirect, send_from_directory, abort, request, jsonify, session, send_file
from datetime import timedelta, datetime, timezone
from quart_session import Session
from quart_cors import cors
import redis.asyncio as redis
import asyncio
import queue
import yaml, aiosqlite, uuid, re, base64
import ujson as json
from typing import Dict, Any

class AppClient:
    def __init__(self, log_system, bot):
        self.bot = bot
        self.logs = log_system
        self.app = Quart(__name__)
        self.app.static_folder = 'static'

        secret_key = self.bot.config.get("secret_key")
        if not secret_key:
            secret_key = secrets.token_hex(32)
            self.bot.config["secret_key"] = secret_key
            self.bot.update_config(self.bot.config)
        self.app.secret_key = secret_key
        
        # Redis连接配置
        # redis_client = redis.Redis(
        #     host='localhost',      # Redis服务器地址
        #     port=6379,            # Redis端口
        #     db=0,                 # Redis数据库编号(0-15)
        #     password=None,        # 如果有密码就填写
        #     decode_responses=True, # 自动解码返回字符串
        #     socket_timeout=5,     # 连接超时(秒)
        #     socket_connect_timeout=5, # 连接建立超时
        #     retry_on_timeout=True, # 超时重试
        # )

        self.app.config.update(
            SESSION_COOKIE_NAME='your_session',
            SESSION_COOKIE_HTTPONLY=True,      # JavaScript无法访问
            SESSION_COOKIE_SECURE=True,       # 仅HTTPS
            SESSION_COOKIE_SAMESITE='None',
            SESSION_COOKIE_DOMAIN=None,          # 限制域名
            # SESSION_PERMANENT=True,             # 使用带过期时间的持久化session
            # PERMANENT_SESSION_LIFETIME=timedelta(days=5),  # 过期时间
            # SESSION_REFRESH_EACH_REQUEST=True,  # 每次请求刷新过期时间
            # SESSION_TYPE='redis',
            # SESSION_REDIS=redis_client,
            # SESSION_KEY_PREFIX='session:',  # Redis键前缀
            # SESSION_USE_SIGNER=True,        # 对session ID签名
            # SESSION_UNIQUE_ID='_id',        # session唯一标识字段
            # SESSION_FILE_DIR='./sessions',       # session文件目录
            # SESSION_FILE_THRESHOLD=20,         # 最大session文件数
            # SESSION_FILE_MODE=0o600,              # 文件权限 (600 in octal)
            QUART_SCHEME='https',                # 强制HTTPS
            MAX_CONTENT_LENGTH=20 * 1024 * 1024,  # 限制请求大小16MB
        )
        # Session(self.app)
        self.app = cors(self.app, 
            allow_origin=["https://god-what-is-that.github.io"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"])

        self.server_thread = None
        self.server = None

        self.nicknames = ["operator", "group_id", "target"]
        self.base_path = os.path.join(os.getcwd(), "static")
        with open('static/config/normal.yml', 'r', encoding='utf-8') as f:
            self.yaml_config = yaml.safe_load(f)
        self.init_config()

        self.AppToLog = AppToLog(bot, log_system, self.yaml_config)

        self.register_routes()
    
    def init_config(self):
        
        config = {
            "formers": self.logs.style.get("former_operator_list"),
            "risk_list": self.logs.style.get("risk_value_list"),
            "operators": self.logs.style.get("operator_list"),
            "group_ids": self.logs.style.get("qq_groups"),
            "operators_nicknames": self.logs.style.get("operator_nicknames_list"),
            "group_ids_nicknames": self.logs.style.get("qq_groups_nicknames_list"),
            "modes_nicknames": self.logs.style.get("mode_list"),
            "modes": list(self.logs.style.get("risk_value_list", {}).keys()),
            "duration_errors": list(self.logs.style.get(f"duration_error{i+1}") for i in range(6))
        }

        self.config = json.dumps(config, ensure_ascii=False)

    def _handle_connection_reset(self, loop, context):
        """
        忽略客户端连接重置错误 (WinError 10054)
        """
        # 检查异常是否是 ConnectionResetError
        exception = context.get('exception')
        if isinstance(exception, ConnectionResetError) and exception.winerror == 10054:
            # 可选：记录一条更简洁的调试日志，而不是让异常堆栈打印出来
            # logging.debug(f"客户端连接已重置: {context.get('message')}")
            pass
        else:
            # 其他异常仍然使用默认的异常处理逻辑
            loop.default_exception_handler(context)

    def register_routes(self):

        @self.app.route('/')
        async def index():
            # return await render_template("index.html")
            return redirect('https://god-what-is-that.github.io/LogSystem/')

        @self.app.route('/api/verify', methods=['POST'])
        async def verify():
            uid = session.get("uid")
            # await self.AppToLog.get_threads_info()
            if not session.get("authed") or not uid or not uid.isdigit() or int(uid) not in self.logs.style.get("operator_list"):
                return jsonify({'status': 'unauthorized'})
            else:
                return await render_template("table.html", config=self.config, yaml=self.yaml_config)
        
        @self.app.errorhandler(404)
        async def page_not_found(e):
            """404错误时重定向到首页"""
            return redirect('/')

        @self.app.errorhandler(405)
        async def method_not_allowed(e):
            """405错误时重定向到首页"""
            return redirect('/')
        
        # @self.app.route('/static/<folder>/<path>')
        # async def get_file(folder, path):
        #     # if folder not in ["images", "config"]:
        #     #     abort(404)

        #     safe_path = await asyncio.to_thread(safe_join, self.base_path, folder, path)
        
        #     # 检查文件是否存在
        #     if not await aiofiles.os.path.exists(safe_path):
        #         abort(404)
        #     return await send_file(safe_path)
        
        @self.app.route('/api/files/<folder>/<path:path>')
        async def get_image(folder, path):
            
            uid = session.get("uid")
            if not session.get("authed") or not uid or not uid.isdigit() or int(uid) not in self.logs.style.get("operator_list"):
                return redirect('/')

            safe_path = await asyncio.to_thread(safe_join, self.base_path, folder, path)
        
            # 检查文件是否存在
            if not await aiofiles.os.path.exists(safe_path):
                abort(404)
            return await send_file(safe_path)
        
        # @self.app.route('/favicon.ico')
        # async def favicon():
        #     # 直接返回你的SVG图标文件
        #     return await send_file('static/images/logo.svg')
        
        # @self.app.route('/.well-known/acme-challenge/<path>')
        # async def get_certificate(path):
        #     abspath = os.path.abspath("certificate/.well-known/acme-challenge")
        #     file = os.path.join(abspath, path)
        #     if await asyncio.to_thread(os.path.exists(file)):
        #         return await send_from_directory(abspath, path)
        #     else:
        #         return "File Not Found", 404
    
        @self.app.route('/api/password', methods=['POST'])
        async def get_password():
            request_data = await request.form
            password = request_data.get('password')
            username = request_data.get('username')
            if password and username:
                if int(username) in self.logs.style.get("operator_list") and password == "nimingtian0123456":
                    session["authed"] = True
                    session["uid"] = username
                    return jsonify({'status': 'success', 'message': 'Logged in'})
                else:
                    # path = os.path.join('static', 'videos', "匿名tian粉丝服。招新。视频广告。.mp4")
                    # return await send_file(path)
                    return jsonify({'status': 'error', 'message': 'Invalid credentials'})
                    
        # 获取log数据
        @self.app.route('/api/data', methods=['POST'])
        async def get_data():

            uid = session.get("uid")
            if not session.get("authed") or not uid or not uid.isdigit() or int(uid) not in self.logs.style.get("operator_list"):
                return redirect('/')
            
            request_data = await request.get_json()
            page = int(request_data.get('page', None)) if request_data else None
            limit = int(request_data.get('limit', None)) if request_data else None
            if not page or not limit:
                return redirect('/')
            
            # 根据上限、页数、总值，计算需要哪些log
            offset = (page - 1) * limit
            total = await self.logs.get_total_logs_count()
            maxpage = (total // limit) + 1
            if offset >= total:
                page = (total + limit - 1) // limit
                offset = (page - 1) * limit
            
            # 获取log内容
            data, others = await self.logs.get_all_logs(limit, offset, False)
            
            return jsonify({
                'success': True,
                'data': data,
                'count_risk': others,
                'pagination': {
                    'page': page,
                    'maxpage': maxpage,
                    'limit': limit,
                    'total': total
                }
            })
        
        @self.app.route('/api/edit', methods=['POST'])
        async def edit_log():

            uid = session.get("uid")
            if not session.get("authed") or not uid or not uid.isdigit() or int(uid) not in self.logs.style.get("operator_list"):
                return redirect('/')
            
            request_data = await request.get_json()
            match = request_data["match"]

            if not match:
                return redirect('/')

            # 根据是否有id判断是编辑还是添加
            action = "edit" if match["id"] else "add"
            success, message, log, old_target = await self.AppToLog.edit_log(match, action)

            # 查询更改前后的目标QQ的risk
            risk = {}
            if success:
                targets = set()
                targets.add(match["target"]["target"])
                if old_target:
                    targets.add(old_target)
                for target in targets:
                    async with aiosqlite.connect(self.logs.db_name) as conn:
                        risk["count"], risk["risk"], risk["state"] = await self.logs.async_get_log_count_by_qq(conn, "target", target, True, True, True)
                    risk[target] = risk

            # 打印所有线程和任务
            # await self.AppToLog.print_all_tasks()
            # await self.AppToLog.get_threads_info()

            return jsonify({"success": success, "message": message, "match": log, "action": action, "risk": risk})

        @self.app.route('/api/delete', methods=['POST'])
        async def delete_log():
            
            uid = session.get("uid")
            if not session.get("authed") or not uid or not uid.isdigit() or int(uid) not in self.logs.style.get("operator_list"):
                return redirect('/')
            
            request_data = await request.get_json()
            id = request_data["id"]

            if not id:
                return redirect('/')

            success, message, target = await self.AppToLog.delete_log(id)

            # 查询目标QQ的risk
            risk = {}
            if success and target:
                async with aiosqlite.connect(self.logs.db_name) as conn:
                    risk["count"], risk["risk"], risk["state"] = await self.logs.async_get_log_count_by_qq(conn, "target", target, True, True, True)
                risk[target] = risk

            return jsonify({"success": success, "message": message, "risk": risk})

    def app_run(self, host, port):

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(self._handle_connection_reset)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        cert_dir = os.path.join(base_dir, "certificate")
        ssl_certfile = os.path.join(cert_dir, "curator.ip-ddns.com-chain.pem")
        ssl_keyfile = os.path.join(cert_dir, "curator.ip-ddns.com-key.pem")
        
        config = uvicorn.Config(
            app=self.app,
            host=host,
            port=port,
            log_level="info",
            reload=False,
            loop="asyncio",
            workers=1,
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile,
            lifespan="off"
        )
        self.server = uvicorn.Server(config)
        # self.server.force_exit = True

        async def serve_until_stopped():
            serve_task = asyncio.create_task(self.server.serve())
            while not self.server.should_exit:
                await asyncio.sleep(0.5)
            try:
                await asyncio.wait_for(serve_task, timeout=1.0)
                print("✅ Uvicorn已自然关闭")
            except asyncio.TimeoutError:
                print("⚠️ 关闭超时，强制取消任务")
                serve_task.cancel()
                try:
                    await serve_task
                except asyncio.CancelledError:
                    pass
            serve_task = None

        loop.run_until_complete(serve_until_stopped())
        loop.stop()
        loop.close()
            
    def start_server(self, host = '0.0.0.0', port = 80):
        if self.server_thread and self.server_thread.is_alive():
            print("⚠️ 服务器已经在运行")
            return
        
        # 创建服务器任务
        self.server_thread = threading.Thread(
            target=self.app_run,
            args=(host, port),
            daemon=True
        )
        self.server_thread.start()
        print("🌐 网站已启动")

    def stop_server(self):
        if self.server_thread is None or self.server is None:
            print("⚠️ 服务器已经关闭")
            return
        print("🛑 停止服务器...")
        self.server.should_exit = True
        s = 1
        while self.server_thread.is_alive():
            self.server_thread.join(timeout=1)
            print(f"已等待{s}秒钟")
            s += 1
        # time.sleep(0.1)
        self.server_thread = None
        self.server = None

        # 清空队列并删除引用
        for _, queue in self.AppToLog.app_queue.items():
            
            while not queue.empty():
                try:
                    queue.get_nowait()
                except:
                    pass

            del queue
    
    def __del__(self):
        self.stop_server()

class AppToLog():
    def __init__(self, bot, logs, yaml_config):
        self.logs = logs
        self.bot = bot
        self.db_name = self.logs.db_name
        self.yaml_config = yaml_config
        self.app_queue = {}

    # 删除log函数
    async def delete_log(self, id):
        success = False
        message = ""
        old_target = None

        # 检查5分钟内是否有其他人更改过此log
        uid = session.get("uid")
        cache = self.logs.cache.get(id)
        if cache and cache != int(uid):
            operators = self.logs.style.get("operator_list")
            message = f"{self.yaml_config.get("edit_error").format(id=id,operator=f'{cache}（{operators.get(cache)}）')}，{self.yaml_config.get("edit_error2")}"

        else:

            # 获取或新建该用户的队列
            bridge = self.app_queue.get(uid)
            if not bridge:
                bridge = queue.Queue()
                self.app_queue[uid] = bridge
                
            # 向同步线程发送消息
            await asyncio.wait_for(asyncio.to_thread(self.bot.message_queue.put, {"post_type": "app", "action": "delete", "id": id, "uid": uid}), timeout=10.0)
            
            respond = await self.wait_for_respond(bridge)
            success = respond["success"]
            message = respond["message"]
            old_target = respond["old_target"]
            self.logs.cache[id] = int(uid)

        return success, message, old_target
    
    # 编辑或添加log函数
    async def edit_log(self, match, action = "edit"):
        success = False
        message = ""
        log = {}
        old_target = None
        id = match["id"]
        
        # 检查5分钟内是否有其他人更改过此log
        uid = session.get("uid")
        if id:
            cache = self.logs.cache.get(id)
            if cache and cache != int(uid):
                operators = self.logs.style.get("operator_list")
                message = f"{self.yaml_config.get("edit_error").format(id=id,operator=f'{cache}（{operators.get(cache)}）')}，{self.yaml_config.get("edit_error2")}"
                return success, message, log, old_target
        
        success, message, log = await self.check_nickname(match, action)

        if success == False:
            return success, message, log, old_target

        # 获取或新建该用户的队列
        bridge = self.app_queue.get(uid)
        if not bridge:
            bridge = queue.Queue()
            self.app_queue[uid] = bridge
            
        # 向同步线程发送消息
        await asyncio.wait_for(asyncio.to_thread(self.bot.message_queue.put, {"post_type": "app", "action": action, "match": log, "uid": uid}), timeout=10.0)

        respond = await self.wait_for_respond(bridge)
        success = respond["success"]
        message = respond["message"]
        log = respond.get("match") or {}
        old_target = respond["old_target"] or log.get("target")
        
        self.logs.cache[id] = int(uid)
        
        return success, message, log, old_target
    
    # 获取昵称并检查参数是否合法
    async def check_nickname(self, match, action = "edit"):
        success = False
        message = ""
        log = {}

        # 检查是否输入了目标昵称
        if match["target"]["nickname"]:
            pass

        elif match["group_id"]["group_id"]:
            
            # 向qq发送异步http请求，获取目标QQ昵称
            name, e = await self.bot.async_get_group_member_nickname(match["group_id"]["group_id"], match["target"]["target"])
            if name is None:
                message = e
                return success, message, log
            
            elif not name:
                retcode = e.get("retcode")
                if retcode == 200:
                    error_msg = self.logs.style.get("get_nickname_error3").format(user_id=match["target"]["target"],group_id=f"{match["group_id"]["group_id"]}（{match["group_id"]["nickname"]}）")
                else:
                    error_msg = self.logs.style.get("get_nickname_error").format(e=e.get("message"))
                message = error_msg
                return success, message, log
            else:
                match["target"]["nickname"] = name

        # 将前端的数据转化成合适的格式
        log = {}
        for field, value in match.items():

            # 有昵称和合并QQ和昵称，没有昵称的先从风格文件获取昵称，理论上除了目标QQ的昵称都写进了风格文件
            if type(value) == dict and field != "images":
                nickname = value["nickname"]
                qq = value[field]
                if qq:
                    if not nickname:
                        if field != "target":
                            nickname = self.logs[f"check{field}"](qq)
                            log[field] = f"{qq}（{nickname}）"
                        else:
                            log[field] = qq = value[field]
                    else:
                        log[field] = f"{qq}（{nickname}）"

                # 老log可能没有群聊QQ
                elif field == "group_id":
                    log[field] = "此条来自xt数据库，没有group_id"

                # 不该有除了群聊QQ没填的QQ号
                else:
                    message = f'{self.yaml_config.get("response_error3")}{field}'
                    return success, message, log
            else:

                # 没有昵称的正常赋值
                if value or (action == "add" and field == "id"):
                    log[field] = value

                # 非禁言模式没有时长
                elif field == "duration" and match.get("mode") != "禁言":
                    log[field] = None

                # 不该有其他没填的参数
                else:
                    message = f'{self.yaml_config.get("response_error3")}{field}'
                    return success, message, log

        success = True
        return success, message, log

    # 等待同步线程的回复
    async def wait_for_respond(self, bridge):
        t = 0
        while True:
            t +=5
            try:
                respond = await asyncio.to_thread(bridge.get, timeout=5.0)
                if respond:
                    return respond
            except Exception as e:
                if t <= 10:
                    continue
                else:
                    return {"success": False, "message": self.yaml_config.get("response_error2")}

    # 下载图片函数
    def download_images(self, id, images):
        message = self.rename_and_clean_files(id, self.logs.image, images["static"])
        if message:
            return message
        for i, image in images["data_url"].items():
            message = self.save_data_url_image(image, f'{id}_{i}')
            if message:
                return message
        return False
    
    def save_data_url_image(self, data_url: str, output_path: str) -> bool:
        """
        将Data URL格式的图片保存为文件
        
        Args:
            data_url: 完整的Data URL字符串，如 "data:image/png;base64,iVBORw0KGgo..."
            output_path: 输出文件路径，如 "image.png"
        
        Returns:
            bool: 是否保存成功
        """
        try:
            # 1. 使用正则分离出Base64数据部分
            # 匹配格式：data:[<媒体类型>];base64,<数据>
            match = re.match(r'^data:image/(\w+);base64,(.+)$', data_url)
            
            if not match:
                print(f"图片Data URL格式不正确，请联系tch：{data_url}")
                return self.yaml_config.get("download_image_error")
            
            # 提取文件扩展名和Base64数据
            image_format, base64_data = match.groups()
            
            # 2. 解码Base64数据
            image_bytes = base64.b64decode(base64_data)
            
            # 3. 写入文件（确保使用正确的扩展名）
            if not output_path.lower().endswith(f'.{image_format}'):
                output_path = f'{output_path.rsplit(".", 1)[0]}.{image_format}'
            output_path = os.path.join(self.logs.image, output_path)
            
            with open(output_path, 'wb') as f:
                f.write(image_bytes)
            
            print(f"图片已保存至：{output_path}")
            return False
            
        except base64.binascii.Error as e:
            print(f"图片Base64解码失败：{e}")
            return self.yaml_config.get(f"download_image_error2{e}")
        except IOError as e:
            print(f"图片写入失败：{e}")
            return self.yaml_config.get(f"download_image_error3{e}")
        except Exception as e:
            print(f"图片下载时出现未知错误：{e}")
            return self.yaml_config.get(f"download_image_error4{e}")
        
    def rename_and_clean_files(self, num, folder_path: str, rename_dict: dict) -> None:
        """
        重命名和清理文件
        
        Args:
            folder_path: 文件夹路径
            rename_dict: 重命名字典，如 {"1": "5_3.jpg", "2": "5_1.png"}
        """

        try:
            # 1. 重命名文件
            for new_num, old_name in rename_dict.items():
                old_path = os.path.join(folder_path, old_name)
                
                if os.path.exists(old_path):
                    # 构建新文件名
                    ext = os.path.splitext(old_name)[1]  # 获取扩展名
                    new_name = f"{num}_{new_num}{ext}"
                    new_path = os.path.join(folder_path, new_name)
                    
                    # 重命名
                    os.rename(old_path, new_path)
                    print(f"重命名: {old_name} -> {new_name}")
            
            # 2. 删除其他以"数字_"开头的文件
            for filename in os.listdir(folder_path):
                if filename.startswith(f"{num}_"):
                    # 检查是否是新重命名的文件
                    is_renamed_file = any(
                        f"{num}_{new_num}{os.path.splitext(old_name)[1]}" == filename
                        for new_num, old_name in rename_dict.items()
                    )
                    
                    if not is_renamed_file:
                        file_path = os.path.join(folder_path, filename)
                        os.remove(file_path)
                        print(f"删除: {filename}")

        except Exception as e:
            print(f"重命名图片时出错：{e}")
            return self.yaml_config.get(f"download_image_error5{e}")
        
    def update_log_by_id(self, id: int, logs: dict):
        """
        更新指定ID的日志字段
        
        Args:
            id: 日志ID
            logs: 要更新的字段字典，如 {"operator": "张三", "reason": "测试"}
        """
        
        try:
            # 构建SET子句
            set_clause = ", ".join([f"{field} = ?" for field in logs.keys()])
            
            # 参数：先logs的值，后id
            params = list(logs.values()) + [id]
            
            # 执行更新
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute(f"UPDATE logs SET {set_clause} WHERE id = ?", params)
                conn.commit()
            
            print(f"✅ 已更新ID {id} 的log")
            return False
            
        except Exception as e:
            print(f"❌ 更新ID为{id}的log失败: {e}")
            return self.yaml_config.get("edit_error3").format(e=e,id=id)
        
    async def print_all_tasks(self):
        """打印所有当前运行的任务"""
        tasks = asyncio.all_tasks()
        print(f"\n当前共有 {len(tasks)} 个任务:")
        
        for i, task in enumerate(tasks, 1):
            print(f"\n任务 #{i}:")
            print(f"  名称: {task.get_name()}")
            print(f"  状态: {task._state}")  # 注意：_state是内部属性
            print(f"  是否完成: {task.done()}")
            print(f"  是否取消: {task.cancelled()}")
            
            # 获取协程信息
            coro = task.get_coro()
            if coro:
                print(f"  协程: {coro}")
            
            # 获取堆栈信息
            try:
                stack = task.get_stack()
                if stack:
                    print(f"  堆栈深度: {len(stack)}")
                    # 打印顶层堆栈帧
                    if stack[-1]:
                        frame = stack[-1]
                        print(f"  执行位置: {frame.f_code.co_filename}:{frame.f_lineno}")
            except:
                pass

    async def get_threads_info(self) -> Dict[str, Any]:
        """
        获取详细的线程信息
        
        Returns:
            包含线程数量、列表和详细信息的字典
        """
        
        # 异步获取
        return await asyncio.to_thread(self.sync_get_threads_info)
    
    def sync_get_threads_info(self):
        """同步获取线程信息"""
        threads = []
        
        for thread in threading.enumerate():
            thread_info = {
                'name': thread.name,
                'ident': thread.ident,
                'daemon': thread.daemon,
                'alive': thread.is_alive(),
                'native_id': getattr(thread, 'native_id', None),  # Python 3.8+
            }
            threads.append(thread_info)
        
        info =  {
            'total_count': len(threads),
            'active_count': threading.active_count(),
            'threads': threads,
            'current_thread': threading.current_thread().name,
            'main_thread': threading.main_thread().name,
        }
        
        print(f"\n📊 线程监控报告:")
        print(f"总线程数: {info['total_count']}")
        print(f"活跃线程数: {info['active_count']}")
        print(f"当前线程: {info['current_thread']}")
        print(f"主线程: {info['main_thread']}")
        
        print("\n📋 所有线程列表:")
        for i, thread in enumerate(info['threads'], 1):
            status = "✅ 活跃" if thread['alive'] else "💀 死亡"
            daemon = "守护线程" if thread['daemon'] else "用户线程"
            print(f"{i:2d}. {thread['name']} ({status}, {daemon}, ID: {thread['ident']})")

if __name__ == '__main__':
    from bot import OneBotClient
    log_system = LogSystem()

    host = "0.0.0.0"
    port_ws = 8081
    port_http = 3001
    WS_URL = f"ws://{host}:{port_ws}"  # WebSocket地址
    HTTP_URL = f"http://{host}:{port_http}"  # HTTP API地址
    ACCESS_TOKEN = None  # 访问令牌（如果有的话）

    bot = OneBotClient(WS_URL, HTTP_URL, ACCESS_TOKEN, log_system)
    app = AppClient(log_system, bot)
    app.start_server('0.0.0.0', 8000)
    try:
        while True:
            time.sleep(60)
            pass
    except KeyboardInterrupt:
        print("\n收到中断信号，正在关闭...")
    finally:
        log_system.stop_backup_scheduler()
        app.stop_server()