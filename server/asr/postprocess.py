"""
ASR 后处理模块
- 口语清洗（重复词合并、数字正则化）
- 断句策略优化（尾静音+标点二次修正）
- 语言路由（预留接口）
"""
import re
from typing import Optional, List, Tuple
from config import settings
from logs import setup_logger

logger = setup_logger(__name__)


class ASRPostProcessor:
    """ASR 后处理器"""
    
    def __init__(self):
        # 口语清洗配置
        self.enable_oral_cleaning = getattr(settings, 'ASR_ENABLE_ORAL_CLEANING', True)
        self.enable_number_normalization = getattr(settings, 'ASR_ENABLE_NUMBER_NORMALIZATION', True)
        self.enable_repeat_removal = getattr(settings, 'ASR_ENABLE_REPEAT_REMOVAL', True)
        
        # 断句策略配置
        self.enable_punctuation_correction = getattr(settings, 'ASR_ENABLE_PUNCTUATION_CORRECTION', True)
        self.min_sentence_length = getattr(settings, 'ASR_MIN_SENTENCE_LENGTH', 3)  # 最小句子长度（字符数）
        
        # 语言路由配置（预留）
        self.enable_lang_id = getattr(settings, 'ASR_ENABLE_LANG_ID', False)
        self.default_lang = getattr(settings, 'ASR_DEFAULT_LANG', 'zh')
    
    def process(self, text: str, has_trailing_silence: bool = False, skip_punctuation_correction: bool = False) -> str:
        """
        处理 ASR 识别结果
        
        Args:
            text: 原始识别文本
            has_trailing_silence: 是否有尾静音（用于断句策略）
            skip_punctuation_correction: 是否跳过断句修正（用于部分结果）
        
        Returns:
            处理后的文本
        """
        if not text or not text.strip():
            return text
        
        # 1. 口语清洗
        if self.enable_oral_cleaning:
            text = self._clean_oral_speech(text)
        
        # 2. 断句策略优化（尾静音+标点二次修正）
        if self.enable_punctuation_correction and not skip_punctuation_correction:
            text = self._correct_punctuation(text, has_trailing_silence)
        
        # 3. 语言路由（预留，未来实现）
        # if self.enable_lang_id:
        #     text = self._route_language(text)
        
        return text.strip()
    
    def clean_oral_speech(self, text: str) -> str:
        """仅进行口语清洗（公共方法，用于部分结果）"""
        if not text or not text.strip():
            return text
        return self._clean_oral_speech(text)
    
    def _clean_oral_speech(self, text: str) -> str:
        """口语清洗"""
        # 1. 重复词合并
        if self.enable_repeat_removal:
            text = self._remove_repeats(text)
        
        # 2. 数字正则化
        if self.enable_number_normalization:
            text = self._normalize_numbers(text)
        
        # 3. 其他口语化处理
        text = self._clean_fillers(text)
        
        return text
    
    def _remove_repeats(self, text: str) -> str:
        """
        移除重复词（口语中常见的重复）
        例如："这个这个" -> "这个"
        """
        # 匹配重复的中文词（2-4字）
        patterns = [
            r'(\S{1,4})\1+',  # 重复1-4字词
        ]
        
        for pattern in patterns:
            text = re.sub(pattern, r'\1', text)
        
        return text
    
    def _normalize_numbers(self, text: str) -> str:
        """
        数字正则化
        例如："一二三" -> "123", "一百二十三" -> "123"
        """
        # 中文数字到阿拉伯数字的映射
        chinese_digits = {
            '零': '0', '一': '1', '二': '2', '三': '3', '四': '4',
            '五': '5', '六': '6', '七': '7', '八': '8', '九': '9',
            '十': '10', '百': '100', '千': '1000', '万': '10000'
        }
        
        # 简单处理：将连续的中文数字转换为阿拉伯数字
        # 更复杂的处理可以使用专门的库如 cn2an
        
        # 处理简单的数字（0-9）
        for chinese, arabic in chinese_digits.items():
            if chinese in ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九']:
                text = text.replace(chinese, arabic)
        
        return text
    
    def _clean_fillers(self, text: str) -> str:
        """
        清理填充词（可选）
        例如："嗯"、"啊"、"那个"等
        """
        # 常见的填充词（可根据需要调整）
        fillers = ['嗯', '啊', '那个', '这个', '就是', '然后']
        
        # 只移除独立的填充词（前后有空格或标点）
        for filler in fillers:
            # 移除独立的填充词
            pattern = rf'\s*{re.escape(filler)}\s*'
            text = re.sub(pattern, ' ', text)
        
        # 清理多余空格
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def _correct_punctuation(self, text: str, has_trailing_silence: bool = False) -> str:
        """
        断句策略优化：尾静音+标点二次修正
        
        策略：
        1. 如果检测到尾静音，但文本末尾没有句号/问号/感叹号，且长度足够，添加句号
        2. 如果文本末尾有标点但长度很短，可能是提前断句，考虑移除或合并
        3. 避免在短句后立即断句
        """
        if not text:
            return text
        
        text = text.strip()
        
        # 检查末尾标点
        ending_punct = ['。', '！', '？', '.', '!', '?']
        has_ending_punct = any(text.endswith(p) for p in ending_punct)
        
        # 策略1：有尾静音但无结束标点，且长度足够 -> 添加句号
        if has_trailing_silence and not has_ending_punct:
            if len(text) >= self.min_sentence_length:
                # 移除末尾的逗号、顿号等，添加句号
                text = re.sub(r'[，、,]\s*$', '', text)
                if not text.endswith('。'):
                    text += '。'
        
        # 策略2：有结束标点但句子很短 -> 可能是提前断句
        # 这里我们保留，但可以记录日志
        if has_ending_punct and len(text) < self.min_sentence_length:
            logger.debug(f"检测到可能的提前断句: {text}")
            # 可选：移除末尾标点，等待更多内容
            # text = re.sub(r'[。！？.!?]\s*$', '', text)
        
        # 策略3：清理多余的标点
        text = re.sub(r'[。！？]{2,}', '。', text)  # 多个结束标点合并为一个
        
        return text
    
    def _route_language(self, text: str) -> str:
        """
        语言路由（预留接口）
        未来可以：
        1. 检测中英文混合
        2. 根据语言切换处理策略
        3. 支持中英混说
        """
        # TODO: 实现语言检测和路由
        # 可以使用 langid 或其他语言检测库
        return text


# 全局后处理器实例
_postprocessor: Optional[ASRPostProcessor] = None


def get_postprocessor() -> ASRPostProcessor:
    """获取后处理器实例（单例）"""
    global _postprocessor
    if _postprocessor is None:
        _postprocessor = ASRPostProcessor()
    return _postprocessor

