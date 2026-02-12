import asyncio, aiohttp
import re
import ujson as json
import websockets
import requests, time
from typing import Dict, Any, Union
import threading, datetime
from queue import Queue
import yaml
from ruamel.yaml import YAML
from logs import LogSystem
from app import AppClient

def read_config(config_path="config.yml"):
    """读取配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        print(f"配置文件 {config_path} 不存在")
        return None
    except yaml.YAMLError as e:
        print(f"解析配置文件出错: {e}")
        return None
config = read_config()
        
class OneBotClient:
    def __init__(self, ws_url: str, http_url: str, access_token: str = None, logs = None):
        """
        初始化OneBot客户端
        
        Args:
            ws_url: WebSocket连接地址 (如: ws://127.0.0.1:6700)
            http_url: HTTP API地址 (如: http://127.0.0.1:5700)
            access_token: 访问令牌（如果需要）
        """
        self.ws_url = ws_url
        self.http_url = http_url.rstrip('/')
        self.access_token = access_token
        self.message_queue = Queue()
        self.running = False
        self.config = config
        self.logs = logs
        
        # 设置HTTP请求头
        self.headers = {'Content-Type': 'application/json'}
        if access_token:
            self.headers['Authorization'] = f'Bearer {access_token}'

    def app_init(self, app):
        self.app = app

    def update_config(self, config, config_path="config.yml"):
        """更新配置文件并保留所有格式（注释、空行等）"""
        try:
            # 第一步：用 ruamel.yaml 重新读取源文件
            yaml = YAML()
            yaml.preserve_quotes = True  # 保留字符串引号样式
            with open(config_path, 'r', encoding='utf-8') as file:
                data_with_comments = yaml.load(file)  # 此对象包含了所有注释和格式

            # 第二步：仅用输入config中的键值去更新（保持其他内容和注释不变）
            # 假设 config 是字典，只更新提供的键
            if isinstance(data_with_comments, dict) and isinstance(config, dict):
                for key, new_value in config.items():
                    # 如果新旧值都是字典，可以递归更新（可选）
                    if (isinstance(new_value, dict) and 
                        key in data_with_comments and 
                        isinstance(data_with_comments[key], dict)):
                        # 递归更新嵌套字典
                        def _deep_update(orig, new):
                            for k, v in new.items():
                                if isinstance(v, dict) and k in orig and isinstance(orig[k], dict):
                                    _deep_update(orig[k], v)
                                else:
                                    orig[k] = v
                        _deep_update(data_with_comments[key], new_value)
                    else:
                        # 直接替换值（ruamel.yaml会处理好类型转换）
                        data_with_comments[key] = new_value
            else:
                # 如果顶层不是字典，整体替换（会丢失注释，尽量避免此情况）
                data_with_comments = config

            # 第三步：将包含注释的data写回文件
            with open(config_path, 'w', encoding='utf-8') as file:
                yaml.dump(data_with_comments, file)

        except FileNotFoundError:
            print(f"配置文件 {config_path} 不存在")
            return None
        except Exception as e:
            print(f"更新配置文件时出错: {e}")
            return None
    
    def _sync_send_message(self, message_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        同步发送HTTP请求到OneBot API
        
        Args:
            message_type: 消息类型（如：send_private_msg, send_group_msg）
            data: 消息数据
            
        Returns:
            API响应结果
        """
        url = f"{self.http_url}/{message_type}"
        try:
            response = requests.post(
                url,
                headers=self.headers,
                data=json.dumps(data),
                timeout=10
            )
            return response.json()
        except Exception as e:
            print(f"发送消息失败: {e}")
            return {"status": "failed", "retcode": -1}
        
    async def _async_send_message(self, message_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步发送HTTP请求到OneBot API
        
        Args:
            message_type: 消息类型（如：send_private_msg, send_group_msg）
            data: 消息数据
            
        Returns:
            API响应结果
        """
        url = f"{self.http_url}/{message_type}"
        
        try:
            # 使用aiohttp进行异步HTTP请求
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=self.headers,
                    json=data,  # aiohttp会自动json序列化
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return await response.json()
        except Exception as e:
            print(f"发送消息失败: {e}")
            return {"status": "failed", "retcode": -1}
    
    def send_private_message(self, user_id: int, message: str, auto_escape: bool = False) -> Dict[str, Any]:
        """
        发送私聊消息
        
        Args:
            user_id: 用户ID
            message: 消息内容
            auto_escape: 是否转义CQ码
            
        Returns:
            API响应结果
        """
        data = {
            "user_id": user_id,
            "message": message,
            "auto_escape": auto_escape
        }
        return self._sync_send_message("send_private_msg", data)
    
    def send_group_message(self, group_id: int, message: str, auto_escape: bool = False) -> Dict[str, Any]:
        """
        发送群聊消息
        
        Args:
            group_id: 群组ID
            message: 消息内容
            auto_escape: 是否转义CQ码
            
        Returns:
            API响应结果
        """
        data = {
            "group_id": group_id,
            "message": message,
            "auto_escape": auto_escape
        }
        return self._sync_send_message("send_group_msg", data)
    
    def process_message_sync(self, message_data: Dict[str, Any]) -> None:
        """
        同步处理消息的回调函数
        
        Args:
            message_data: 收到的消息数据
        """
        try:
            post_type = message_data.get('post_type', '')
            
            if post_type == 'message':
                # 同步处理
                message_type = message_data.get('message_type', '')
                message = message_data.get('message', '')
                user_id = message_data.get('user_id', '')
                # self_id = message_data.get('self_id', '')
                
                
                # 私聊消息
                if message_type == 'private':
                    # self.handle_message(message_data, 'private')
                    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 收到私人消息，发送者: {user_id}，消息内容: {message}")
                
                # 群聊消息
                elif message_type == 'group':
                    self.handle_message(message_data, 'group')
                    return
            
            elif post_type == 'message_sent':
                # self.handle_message_sent(message_data)
                return

            # 与网页对接
            elif post_type == "app" and message_data.get("uid"):
                self.handle_app(message_data)
                return

            # 申请
            elif post_type == 'request':
                self.handle_request(message_data)
                return
                    
        except Exception as e:
            import traceback
            print(f"处理消息时出错: {e}")
            traceback.print_exc()
    
    def approve_group_request(self, flag: str, sub_type: str = "add") -> Dict[str, Any]:
        """
        批准加群申请
        
        Args:
            flag: 请求标识符（从请求数据中获取）
            sub_type: 请求子类型，通常是 "add"（加群申请）
            
        Returns:
            API响应结果
        """
        data = {
            "flag": flag,
            "sub_type": sub_type,
            "approve": True,    # True表示同意
            "reason": ""        # 批准时通常不需要理由
        }
        return self._sync_send_message("set_group_add_request", data)

    def reject_group_request(self, flag: str, reason: str = "", sub_type: str = "add") -> Dict[str, Any]:
        """
        拒绝加群申请
        
        Args:
            flag: 请求标识符
            reason: 拒绝理由（可选）
            sub_type: 请求子类型，通常是 "add"
            
        Returns:
            API响应结果
        """
        data = {
            "flag": flag,
            "sub_type": sub_type,
            "approve": False,   # False表示拒绝
            "reason": reason    # 拒绝理由
        }
        return self._sync_send_message("set_group_add_request", data)

    def get_group_member_nickname(self, group_id: str, user_id: str) -> str:
        """
        获取群成员在群里的昵称
        
        Args:
            group_id: 群ID（字符串）
            user_id: 用户QQ ID（字符串）
            
        Returns:
            群成员昵称，如果获取失败则返回空字符串
        """
        try:
            # 构建请求数据
            data = {
                "group_id": int(group_id),
                "user_id": int(user_id),
                "no_cache": True  # 不使用缓存，获取最新数据
            }
            
            # 发送HTTP请求
            response = self._sync_send_message("get_group_member_info", data)
            
            # 解析响应
            if response.get("status") == "ok" and response.get("retcode") == 0:
                member_info = response.get("data", {})
                nickname = member_info.get("card", "")  # 群名片
                if not nickname:  # 如果群名片为空，使用昵称
                    nickname = member_info.get("nickname")
                return nickname , None
            else:
                # print(f"获取群成员信息失败: {response}")
                return False, response
                
        except Exception as e:
            # print(f"网络请求异常: {e}")
            return None, e
        
    async def async_get_group_member_nickname(self, group_id: str, user_id: str) -> str:
        """
        获取群成员在群里的昵称
        
        Args:
            group_id: 群ID（字符串）
            user_id: 用户QQ ID（字符串）
            
        Returns:
            群成员昵称，如果获取失败则返回空字符串
        """
        try:
            # 构建请求数据
            data = {
                "group_id": int(group_id),
                "user_id": int(user_id),
                "no_cache": True  # 不使用缓存，获取最新数据
            }
            
            # 发送HTTP请求
            response = await self._async_send_message("get_group_member_info", data)
            
            # 解析响应
            if response.get("status") == "ok" and response.get("retcode") == 0:
                member_info = response.get("data", {})
                nickname = member_info.get("card", "")  # 群名片
                if not nickname:  # 如果群名片为空，使用昵称
                    nickname = member_info.get("nickname")
                return nickname , None
            else:
                # print(f"获取群成员信息失败: {response}")
                return False, response
                
        except Exception as e:
            # print(f"网络请求异常: {e}")
            return None, e
        
    def get_group_avatar_url(self, group_id: int) -> str:
        """
        获取QQ群头像URL
        
        Args:
            group_id: QQ群号
            
        Returns:
            群头像URL，失败时返回空字符串
        """
        try:
            # 构建获取群信息的API URL
            url = f"{self.http_url}/get_group_info"
            
            # 请求参数
            data = {
                "group_id": group_id,
                "no_cache": True  # 不使用缓存，获取最新信息
            }
            
            # 发送请求
            response = requests.post(
                url,
                headers=self.headers,
                data=json.dumps(data),
                timeout=10
            )
            
            result = response.json()
            
            # 检查响应状态
            if result.get("status") == "ok" and "data" in result:
                group_info = result["data"]
                
                # 方法1：如果有群头像字段（某些OneBot实现会有）
                if "avatar_url" in group_info:
                    return group_info["avatar_url"]
                
                # 方法2：如果没有专用字段，可以通过群号拼接URL
                # QQ群头像通常可以通过以下方式获取
                # 注意：这种URL可能不稳定，不同平台可能不同
            qq_number = str(group_id)
            return f"https://p.qlogo.cn/gh/{qq_number}/{qq_number}/640"
            
        except Exception as e:
            print(f"获取群头像失败: {e}")
            return ""
    
    def mute_member(self, group_id: Union[str, int], target_id: Union[str, int], dura: Union[str, int] = None) -> Dict[str, Any]:
        """
        在QQ群中禁言目标成员
        
        Args:
            group_id: QQ群号
            target_id: 目标QQ号
            duration: 禁言时长（秒），默认600秒（10分钟）
                    特殊值：0表示解除禁言
        Returns:
            message: 回复消息
        """
        
        if dura is None:
            duration = 600
        elif isinstance(dura, (int, float)):
            pass
        elif dura.isdigit():
            duration = int(dura)
        else:
            pattern = r'^\d+(\.\d)?[hsmdMw]$'
            if not bool(re.match(pattern, str(dura))):
                return self.logs.style.get("duration_error").format(duration=dura)
            unit = dura[-1]
            number = float(dura[:-1])
            if unit == "s":
                duration = number
            elif unit == "m":
                duration = number * 60
            elif unit == "h":
                duration = number * 3600
            elif unit == "d":
                duration = number * 3600 * 24
            elif unit == "M":
                duration = 2592000

        data = {
            "group_id": group_id,
            "user_id": target_id,
            "duration": duration
        }

        try:
            response = self._sync_send_message("set_group_ban", data)
        
            # 解析响应
            if response.get("status") == "ok" and response.get("retcode") == 0:
                message = self.logs.style.get("execute_success").format(target=target_id,group=group_id,mode="禁言")
                message = f"{message}{dura}"
                return message
            else:
                print(response)
                retcode = response.get("retcode")
                if retcode == 200:
                    error_msg = self.logs.style.get("get_nickname_error3").format(user_id=target_id,group_id=f"{group_id}（{self.logs.style.get("operator_list")[group_id]}）")
                else:
                    error_msg = self.logs.style.get("execute_error").format(mode="禁言",e=response.get("message"))
                return error_msg
                
        except Exception as e:
            # print(f"网络请求异常: {e}")
            return e
        
    def kick_member(self, group_id: Union[str, int], target_id: Union[str, int], reject_add_request: bool = False) -> Dict[str, Any]:
        """
        在QQ群中踢出目标成员
        
        Args:
            group_id: QQ群号
            target_id: 目标QQ号
            
        Returns:
            message: 回复消息
        """
        
        kick_data = {
            "group_id": group_id,
            "user_id": target_id,
            "reject_add_request": reject_add_request
        }
        mode = "踢出" if not reject_add_request else "拉黑"
        
        try:
            response = self._sync_send_message("set_group_kick", kick_data)
        
            # 解析响应
            if response.get("status") == "ok" and response.get("retcode") == 0:
                return self.logs.style.get("execute_success").format(target=target_id,group=group_id,mode=mode)
            else:
                retcode = response.get("retcode")
                if retcode == 200:
                    error_msg = self.logs.style.get("get_nickname_error3").format(user_id=target_id,group_id=f"{group_id}（{self.logs.style.get("operator_list")[group_id]}）")
                else:
                    error_msg = self.logs.style.get("execute_error").format(mode=mode,e=response.get("message"))
                return error_msg
                
        except Exception as e:
            # print(f"网络请求异常: {e}")
            return e

    def handle_message_sent(self, data):
        pass

    def handle_message(self, data, mode):
        """
        处理群聊消息，对接log系统
        
        Args:
            data: 消息数据
            mode: 群聊还是私聊，私聊只限于测试
            
        Returns:
            None
        """

        group_id = data.get("group_id", data.get('user_id'))
        raw_message = data.get("raw_message")
        keyword = config.get("keyword", "/")

        if (group_id == config.get("QQgroup") or mode == 'private') and raw_message and raw_message.startswith(keyword):
            keywords = self.logs.style.get("log_list")
            ifkeyword = False

            
            # 检查开头是否有关键词
            for key in keywords:
                if raw_message.startswith(f'{keyword}{key}'):
                    ifkeyword = True
                    break
            if ifkeyword:
                message = data.get("message")
                # id = await self.get_group_member_nickname("963462616", "3120231417")
                # print(id)
                # response = self.send_group_message(group_id, "你好")
                operator = data.get("user_id", "未知qq")
                print(f'{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 收到消息：{raw_message}')
                images = {}
                count = 1

                # 打包图片url
                for i in message:
                    if i.get("type") == "image":
                        images[count] = i.get("data", {}).get("url")
                        count = count + 1

                # 发送给log系统
                respond = self.logs.process_command(raw_message, images, operator)

                # 回复消息
                response = self.send_group_message(group_id, f'[CQ:at,qq={data.get("user_id")}] {respond}') if mode == 'group' else self.send_private_message(group_id, f'[CQ:at,qq={data.get("user_id")}] {respond}')
                print(f'{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 回复消息：{respond}')
        
        # 转发粉丝服解绑信息
        elif group_id == 1048699506 and raw_message and (raw_message == "#解绑" or raw_message == "#绑定 解绑"):
            qq = data.get("user_id", "未知qq")
            nickname = data.get("sender", {}).get("card", "无")
            message = f"群 1048699506 有成员解绑\nQQ号: {qq}\n曾绑定玩家: {nickname}"
            response = self.send_group_message(config.get("QQgroup"), message)

    def handle_request(self, message_data):
        """
        处理粉丝服入群申请
        
        Args:
            message_data: 消息数据
            
        Returns:
            None
        """

        # 检查是否是加群申请
        if message_data.get("request_type", None) == "group" and message_data.get("sub_type", None) == "add":
            respond = ''
            group_id = message_data.get("group_id", None)

            # 检查是否有消息标识符
            flag = message_data.get("flag", None)
            if flag is None:
                respond = self.logs.style.get("flag_not_found").format(data=str(message_data))
                
            answer = message_data.get("comment", None).split('答案：', 1)[1].strip()
            qq = message_data.get("user_id", None)

            # 检查是否是粉丝服群
            if group_id == self.config.get("fanserver"):

                # respond是发到管理群的，response是发给申请者的
                response = ""
                respond = ""
                groups = self.logs.style.get("allowed_group_list", {})
                name = None
                e = None

                # 是否要拒绝申请，默认为否
                ifreject = False

                # 检查申请者是否在大群列表的大群内
                for i in groups:
                    name, e = self.get_group_member_nickname(i, qq)

                    # 如果检查到在某个群，停止检查其他群
                    if name:
                        break

                # 昵称为None说明网络有问题
                if name is None:
                    respond = e
                    response = None

                # name为False时
                elif not name:
                    retcode = e.get("retcode")

                    # 请者不在任何大群内，或者机器人账号不在该群，由于没有设置ifreject为True，该情况不会自动拒绝入群
                    if retcode == 200:
                        respond = self.logs.style.get("not_in_group").format(qq=qq)
                        response = self.logs.style.get("not_in_group_response")

                    # 未知错误
                    else:
                        respond = self.logs.style.get("get_nickname_error").format(e=e.get("message"))
                        response = None

                # 如果在，检查mc_id是否合法
                else:
                    pattern = "^[a-zA-Z0-9_]{3,16}$"
                    qq = f'{qq}（{name}）'

                    # 不合法则拒绝入群
                    if not bool(re.match(pattern, answer)):
                        response = self.logs.style.get("mc_id_error_response")
                        respond = self.logs.style.get("mc_id_error").format(qq=qq,id=answer)
                        ifreject = True
                    else:
                        respond = self.logs.style.get("join_group_success").format(qq=qq,id=answer)

                # 提示信息发到管理群
                group_id = config.get("QQgroup")
                self.send_group_message(group_id, respond)

                # 回复信息为None则不做处理
                if response is None:
                    pass

                # 不存在回复消息则同意申请
                elif not response:
                    result = self.approve_group_request(flag)
                    if not (result.get("status") == "ok" and result.get("retcode") == 0):
                        self.send_group_message(group_id, self.logs.style.get("handle_group_request_error").format(qq=qq,e=result.get("message")))

                # 存在回复消息且ifreject为True则拒绝申请，ifreject专门为了不在大群的人设计
                else:
                    if ifreject:
                        result = self.reject_group_request(flag, response)
                        if not (result.get("status") == "ok" and result.get("retcode") == 0):
                            self.send_group_message(group_id, self.logs.style.get("handle_group_request_error").format(qq=qq,e=result.get("message")))

    def handle_app(self, message_data):
        """
        处理网页申请，对接log系统
        
        Args:
            message_data: 消息数据
            
        Returns:
            None
        """

        uid = message_data.get("uid")
        action = message_data.get("action")

        # 如果是编辑模式
        if action == "edit":
            match = message_data.get("match")
            id = match.get("id")
            images = match.pop("images")
            success = False
            message = ""
            new_log = {}
            old_target = None

            # 获取log详情，检查此log是否存在，可能有人在5分钟以外改了原log_id
            log = self.logs.get_log_by_id_dict(id, False)
            if log is None:
                message = f"{self.logs.style.get("details_none").format(id=id)}，{self.app.yaml_config.get("edit_error2")}"
            else:
                old_target = log["target"].split('（')[0]

                # 最后确认新log是否有字段没填，有的话该字段不变，避免有人在5分钟以外新加了该字段
                for field, value in log.items():
                    if not match[field]:
                        match[field] = value

                # 更新log以及下载图片
                message = self.app.AppToLog.update_log_by_id(id, match)
                if not message:
                    message = self.app.AppToLog.download_images(id, images)
                    if not message:
                        success = True
                        message = self.app.yaml_config.get("edit_success").format(id=id)
                        new_log = match
                        new_log["images_path"] = self.logs.get_images_paths(id, False)

            self.app.AppToLog.app_queue[uid].put({"success": success, "message": message, "match": new_log, "old_target": old_target})

        # 如果是删除模式
        elif action == "delete":
            id = message_data.get("id")
            success = False
            old_target = None

            # 获取log详情，检查此log是否存在，可能有人在5分钟以外改了原log_id
            log = self.logs.get_log_by_id_dict(id, False)
            if log is None:
                message = f"{self.logs.style.get("details_none").format(id=id)}，{self.app.yaml_config.get("edit_error2")}"
            else:
                old_target = log["target"].split('（')[0]
                success = True
                e, message = self.logs.delete_log(id)
                if e:
                    success = False

            self.app.AppToLog.app_queue[uid].put({"success": success, "message": message, "old_target": old_target})

        # 如果是添加模式
        elif action == "add":
            success = False
            match = message_data.get("match")
            images = match.pop("images")

            # 添加该log
            id = self.logs.add_log(match)

            # 下载图片并命名
            message = self.logs.delete_image(id)
            if not message:
                for i, url in images["data_url"].items():
                    message = self.app.AppToLog.save_data_url_image(url, f'{id}_{i}')
                    if message:
                        break
                if not message:
                    match["id"] = id
                    success = True
                    message = self.app.yaml_config.get("add_success").format(id=id)
                    match["images_path"] = self.logs.get_images_paths(id, False)

            self.app.AppToLog.app_queue[uid].put({"success": success, "message": message, "match": match, "old_target": None})

    def message_handler(self) -> None:
        """
        消息处理线程函数，从队列中取出消息并同步处理
        """
        while self.running:
            try:
                message_data = self.message_queue.get(timeout=1.0)
                if message_data:
                    # 调用同步处理函数
                    self.process_message_sync(message_data)
            except:
                continue

    async def _listen_websocket(self) -> None:
        """
        异步监听WebSocket连接
        """

        ws_headers = {}
        if self.access_token:
            ws_headers['Authorization'] = f'Bearer {self.access_token}'
        
        reconnect_delay = config.get("reconnect_delay")  # 重连间隔（秒）
        reconnect_count = 0   # 重连次数
        
        while self.running:
            try:
                # 连接WebSocket
                print(f"正在连接WebSocket: {self.ws_url}")
                async with websockets.connect(
                    self.ws_url,
                    # extra_headers=ws_headers,
                    ping_interval=20,  # 每20秒发送一次ping
                    ping_timeout=10,   # ping超时10秒
                    close_timeout=1    # 关闭超时1秒
                ) as websocket:
                    
                    print(f"✓ 已连接到WebSocket: {self.ws_url}")
                    reconnect_count = 0  # 重置重连计数
                    
                    while self.running:
                        try:
                            # 接收消息
                            # await self.app.AppToLog.get_threads_info()
                            message = await websocket.recv()
                            message_data = json.loads(message)
                            
                            # 将消息放入队列供同步处理
                            self.message_queue.put(message_data)
                            
                        except websockets.exceptions.ConnectionClosed as e:
                            print(e)
                            print(f"WebSocket连接已关闭: 状态码：{e.code}, 原因：{e.reason if e.reason else e}")
                            
                            # 如果是正常关闭，可能不需要重连
                            if e.code == 1000:  # 正常关闭
                                print("WebSocket正常关闭，退出连接循环")
                                return
                            
                            # 非正常关闭，跳出内层循环尝试重连
                            break
                            
                        except asyncio.CancelledError:
                            print("WebSocket任务被取消")
                            return
                            
                        except Exception as e:
                            print(f"接收消息时出错: {e}")
                            # 继续循环，不中断连接
                            continue
                    
                    # 连接关闭后，如果不是因为self.running=False，则尝试重连
                    if self.running:
                        reconnect_count += 1
                        print(f"连接断开，{reconnect_delay}秒后尝试第{reconnect_count}次重连...")
                        await asyncio.sleep(reconnect_delay)
                        
            except websockets.exceptions.InvalidURI:
                print(f"无效的WebSocket地址: {self.ws_url}")
                return
                
            except websockets.exceptions.InvalidHandshake:
                print("WebSocket握手失败，请检查访问令牌或权限")
                reconnect_count += 1
                if self.running:
                    print(f"{reconnect_delay}秒后尝试第{reconnect_count}次重连...")
                    await asyncio.sleep(reconnect_delay)
                    
            except ConnectionRefusedError:
                print("连接被拒绝，请检查OneBot是否正在运行")
                reconnect_count += 1
                if self.running:
                    try:
                        print(f"{reconnect_delay}秒后尝试第{reconnect_count}次重连...")
                        await asyncio.sleep(reconnect_delay)
                    except asyncio.CancelledError:
                        print("重连等待被取消，退出")
                        return
                    
            except asyncio.CancelledError:
                print("连接任务被取消")
                return
                
            except Exception as e:
                print(f"连接WebSocket失败: {e}")
                reconnect_count += 1
                if self.running:
                    try:
                        print(f"{reconnect_delay}秒后尝试第{reconnect_count}次重连...")
                        await asyncio.sleep(reconnect_delay)
                    except asyncio.CancelledError:
                        print("重连等待被取消，退出")
                        return

    def start(self) -> None:
        """
        启动客户端
        """
        self.running = True
        
        # 启动消息处理线程
        message_thread = threading.Thread(target=self.message_handler)
        message_thread.daemon = True
        message_thread.start()
        print("消息处理线程已启动")
        app.AppToLog.sync_get_threads_info()
        
        # 创建异步事件循环
        self.loop = asyncio.new_event_loop()  # 保存到实例变量
        asyncio.set_event_loop(self.loop)
        
        try:
            # 创建任务并运行
            self.tasks = [
                self.loop.create_task(self._listen_websocket()),
            ]
            
            # 运行直到所有任务完成
            self.loop.run_until_complete(asyncio.gather(*self.tasks))
            
        except KeyboardInterrupt:
            print("\n收到中断信号，正在关闭...")
        except Exception as e:
            print(f"运行出错: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.logs.stop_backup_scheduler()
            self.app.stop_server()
            self.stop()
    
    def stop(self) -> None:
        """
        停止客户端 - 优雅关闭
        """
        if not self.running:
            return
            
        print("正在关闭客户端...")
        self.running = False
        
        # 取消所有异步任务
        if hasattr(self, 'loop') and self.loop and not self.loop.is_closed():
            # 获取所有未完成的任务
            pending_tasks = [task for task in asyncio.all_tasks(self.loop) if not task.done()]
            
            # 取消所有任务
            for task in pending_tasks:
                task.cancel()
            
            # 等待所有任务完成（或取消）
            if pending_tasks:
                try:
                    self.loop.run_until_complete(
                        asyncio.gather(*pending_tasks, return_exceptions=True)
                    )
                except:
                    pass
            
            # 关闭事件循环
            try:
                self.loop.close()
            except:
                pass
        
        # 清空消息队列
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
            except:
                pass
        
        print("客户端已停止")

    def __del__(self):
        self.stop()


# 示例使用
if __name__ == "__main__":
    host = config.get("host") or "0.0.0.0"
    port_ws = config.get("port_ws") or 8081
    port_http = config.get("port_http") or 3001
    WS_URL = f"ws://{host}:{port_ws}"  # WebSocket地址
    HTTP_URL = f"http://{host}:{port_http}"  # HTTP API地址
    ACCESS_TOKEN = None  # 访问令牌（如果有的话）
    
    # 创建客户端实例
    logs = LogSystem(config.get("db_name"), config.get("style", "normal"), config.get("styles", "styles"), config.get("image", r"static\images"), config.get("backup_file", "backup"))
    client = OneBotClient(WS_URL, HTTP_URL, ACCESS_TOKEN, logs)
    logs.bot_init(client)
    
    app = AppClient(logs, client)
    client.app_init(app)
    # print("网站开之前")
    # app.AppToLog.sync_get_threads_info()
    app.start_server('0.0.0.0', 8000)
    # print("网站开之后")
    # app.AppToLog.sync_get_threads_info()
    
    # 启动客户端
    client.start()