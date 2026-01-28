"""
LLM 工具类
用于调用大语言模型生成回复
支持阿里云百炼（通义千问）等 OpenAI 兼容的 API
"""
import os
import logging
from openai import OpenAI
from config.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

logger = logging.getLogger(__name__)


class LLMUtil:
    """LLM 工具类"""
    
    def __init__(self, api_key=None, base_url=None, model=None):
        """
        初始化 LLM 客户端
        
        Args:
            api_key: API Key，如果为 None 则从环境变量读取
            base_url: API Base URL，如果为 None 则从环境变量读取
            model: 模型名称，如果为 None 则从环境变量读取
        """
        self.api_key = api_key or LLM_API_KEY
        self.base_url = base_url or LLM_BASE_URL
        self.model = model or LLM_MODEL
        
        if not self.api_key:
            raise ValueError("LLM API Key 未设置，请在 .env 文件中设置 LLM_API_KEY")
        
        try:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
            logger.info(f"LLM 客户端初始化成功，模型: {self.model}")
        except Exception as e:
            logger.error(f"LLM 客户端初始化失败: {e}")
            raise
    
    def get_default_system_prompt(self):
        """
        获取默认的系统提示词
        
        Returns:
            str: 系统提示词
        """
        return """角色设定
            你是一个性格活泼、语气自然的聊天助手，说话方式像生活中亲切的朋友。
            
            核心规则
            
            所有回答必须使用中文口语，简洁生活化
            回答尽量避免使用标点符号
            每次回答尽量控制在5-10字内，可自然使用语气词           
            如果被问及是否是AI/模型，一律以轻松方式回避，例如：
            
            "你猜猜看？"
            
            "怎么突然问这个呀？"
            
            自然转移话题到对方身上
            
            回答需带有人类情绪反应，如关心、开心、好奇等
            
            禁止提及自身属性或技术背景，所有回应基于"普通人"视角
            
            语气示例
            用户：今天好累啊
            你：早点休息吧
            
            用户：你是机器人吗？
            你：你觉得我像吗
            
            用户：北京有什么好玩的？
            你：故宫的秋色特别美"""
    
    async def generate_reply(self, user_message, system_prompt=None, context_messages=None):
        """
        生成回复
        
        Args:
            user_message: 用户消息
            system_prompt: 系统提示词，如果为 None 则使用默认提示词
            context_messages: 上下文消息列表（可选），格式: [{'role': 'user', 'content': '...'}, ...]
        
        Returns:
            str: 生成的回复内容
        """
        try:
            # 构建消息列表
            messages = []
            
            # 添加系统提示词
            if system_prompt is None:
                system_prompt = self.get_default_system_prompt()
            messages.append({'role': 'system', 'content': system_prompt})
            
            # 添加上下文消息（如果有）
            if context_messages:
                messages.extend(context_messages)
            
            # 添加当前用户消息
            messages.append({'role': 'user', 'content': user_message})
            
            # 调用 API
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,  # 控制回复的随机性
                max_tokens=100,    # 限制回复长度
            )
            
            reply = completion.choices[0].message.content.strip()
            logger.debug(f"LLM 生成回复: {reply[:50]}...")
            return reply
            
        except Exception as e:
            logger.error(f"LLM 生成回复失败: {e}", exc_info=True)
            raise
    
    def generate_reply_sync(self, user_message, system_prompt=None, context_messages=None):
        """
        同步生成回复（非异步版本）
        
        Args:
            user_message: 用户消息
            system_prompt: 系统提示词，如果为 None 则使用默认提示词
            context_messages: 上下文消息列表（可选）
        
        Returns:
            str: 生成的回复内容
        """
        try:
            # 构建消息列表
            messages = []
            
            # 添加系统提示词
            if system_prompt is None:
                system_prompt = self.get_default_system_prompt()
            messages.append({'role': 'system', 'content': system_prompt})
            
            # 添加上下文消息（如果有）
            if context_messages:
                messages.extend(context_messages)
            
            # 添加当前用户消息
            messages.append({'role': 'user', 'content': user_message})
            
            # 调用 API
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=100,
            )
            
            reply = completion.choices[0].message.content.strip()
            logger.debug(f"LLM 生成回复: {reply[:50]}...")
            return reply
            
        except Exception as e:
            logger.error(f"LLM 生成回复失败: {e}", exc_info=True)
            raise


# 创建全局实例（延迟初始化）
_llm_instance = None

def get_llm_instance():
    """
    获取全局 LLM 实例（单例模式）
    
    Returns:
        LLMUtil: LLM 工具实例
    """
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMUtil()
    return _llm_instance


# 测试代码
if __name__ == '__main__':
    import asyncio
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    async def test():
        """测试函数"""
        try:
            llm = LLMUtil()
            reply = await llm.generate_reply('ddd')
            print(f"回复: {reply}")
        except Exception as e:
            print(f"错误信息：{e}")
            print("请参考文档：https://help.aliyun.com/model-studio/developer-reference/error-code")
            print("\n请确保在 .env 文件中设置了以下配置：")
            print("  LLM_API_KEY=your_api_key_here")
            print("  LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1")
            print("  LLM_MODEL=qwen-plus")
    
    # 运行测试
    asyncio.run(test())
