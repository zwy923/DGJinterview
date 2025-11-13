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
            处理后的文本（如果无效则返回空字符串）
        """
        if not text or not text.strip():
            return ""
        
        # 0. 预过滤：过滤掉明显无效的结果
        text = self._prefilter_invalid(text)
        if not text:
            return ""
        
        # 1. 口语清洗
        if self.enable_oral_cleaning:
            text = self._clean_oral_speech(text)
        
        # 2. 断句策略优化（尾静音+标点二次修正）
        if self.enable_punctuation_correction and not skip_punctuation_correction:
            text = self._correct_punctuation(text, has_trailing_silence)
        
        # 3. 后过滤：再次检查有效性
        text = self._postfilter_invalid(text)
        
        # 4. 语言路由（预留，未来实现）
        # if self.enable_lang_id:
        #     text = self._route_language(text)
        
        return text.strip()
    
    def _prefilter_invalid(self, text: str) -> str:
        """
        预过滤：过滤掉明显无效的识别结果
        """
        text = text.strip()
        if not text:
            return ""
        
        # 过滤掉只有标点的结果
        if re.match(r'^[。！？，、\s]+$', text):
            return ""
        
        # 过滤掉只有单个字符且是标点的结果
        if len(text) == 1 and text in '。！？，、':
            return ""
        
        # 过滤掉太短的结果（少于最小长度，且不是常见短词）
        if len(text) < self.min_sentence_length:
            # 允许的短词列表
            allowed_short_words = {'是', '不', '对', '好', '行', '嗯', '啊', '错', '有', '没', '可以', '不行', '没有'}
            if text not in allowed_short_words:
                return ""
        
        return text
    
    def _postfilter_invalid(self, text: str) -> str:
        """
        后过滤：处理后的再次检查
        """
        text = text.strip()
        if not text:
            return ""
        
        # 再次检查长度（处理后可能变短）
        if len(text) < self.min_sentence_length:
            # 允许的短词列表
            allowed_short_words = {'是', '不', '对', '好', '行', '嗯', '啊', '错', '有', '没', '可以', '不行', '没有'}
            if text not in allowed_short_words:
                return ""
        
        # 检查是否只有标点和空格
        if re.match(r'^[。！？，、\s]+$', text):
            return ""
        
        return text
    
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
        移除重复词（口语中常见的重复，更保守的策略）
        例如："这个这个" -> "这个"，但保留有意义的重复如"好好"
        """
        # 只移除连续重复2次以上的词（避免误删有意义的重复）
        # 匹配重复的中文词（1-3字），至少重复2次
        patterns = [
            r'(\S{1,3})\1{2,}',  # 重复3次以上（更保守）
        ]
        
        for pattern in patterns:
            text = re.sub(pattern, r'\1', text)
        
        # 特殊处理：移除常见的口语重复（如"这个这个"、"那个那个"）
        common_repeats = [
            r'(这个)\1+', r'(那个)\1+', r'(就是)\1+', r'(然后)\1+', r'(还有)\1+'
        ]
        for pattern in common_repeats:
            text = re.sub(pattern, r'\1', text)
        
        return text
    
    def _normalize_numbers(self, text: str) -> str:
        """
        数字正则化（改进版：处理常见口语数字错误）
        例如："1下" -> "一下", "1个" -> "一个", "2个" -> "两个"
        """
        # 常见口语数字错误修正
        number_corrections = {
            r'1([下个次点])': r'一\1',  # "1下" -> "一下", "1个" -> "一个"
            r'2([下个次点])': r'两\1',  # "2下" -> "两下", "2个" -> "两个"
            r'3([下个次点])': r'三\1',  # "3下" -> "三下"
            r'4([下个次点])': r'四\1',
            r'5([下个次点])': r'五\1',
            r'6([下个次点])': r'六\1',
            r'7([下个次点])': r'七\1',
            r'8([下个次点])': r'八\1',
            r'9([下个次点])': r'九\1',
            r'10([下个次点])': r'十\1',  # "10个" -> "十个"
        }
        
        for pattern, replacement in number_corrections.items():
            text = re.sub(pattern, replacement, text)
        
        # 中文数字到阿拉伯数字的映射（保留原有功能，但更保守）
        chinese_digits = {
            '零': '0', '一': '1', '二': '2', '三': '3', '四': '4',
            '五': '5', '六': '6', '七': '7', '八': '8', '九': '9',
        }
        
        # 只在明确是数字上下文时才转换（更保守）
        # 这里暂时保留，但可以后续优化
        
        return text
    
    def _clean_fillers(self, text: str) -> str:
        """
        清理填充词（更保守的策略，避免误删有用信息）
        只移除明显的填充词，保留可能有意义的词
        """
        # 只移除明显的填充词（更保守的列表）
        obvious_fillers = ['嗯', '啊', '呃', '那个那个', '这个这个']
        
        # 只移除独立的填充词（前后有空格、标点或边界）
        for filler in obvious_fillers:
            # 修复：使用固定宽度的lookbehind，分别处理开头、中间、结尾的情况
            escaped_filler = re.escape(filler)
            
            # 1. 开头的填充词（后面是空格或标点）
            pattern1 = rf'^{escaped_filler}(?=[\s，。！？、])'
            text = re.sub(pattern1, '', text)
            
            # 2. 中间的填充词（前后都是空格或标点）
            pattern2 = rf'(?<=[\s，。！？、]){escaped_filler}(?=[\s，。！？、])'
            text = re.sub(pattern2, '', text)
            
            # 3. 结尾的填充词（前面是空格或标点）
            pattern3 = rf'(?<=[\s，。！？、]){escaped_filler}$'
            text = re.sub(pattern3, '', text)
            
            # 4. 整个文本就是填充词
            if text.strip() == filler:
                text = ''
        
        # 清理多余空格（但保留标点后的空格）
        text = re.sub(r' +', ' ', text)  # 多个空格合并为一个
        text = re.sub(r' ([，。！？、])', r'\1', text)  # 移除标点前的空格
        
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
        # 更保守：只记录日志，不自动移除（避免误删）
        if has_ending_punct and len(text) < self.min_sentence_length:
            logger.debug(f"检测到短句: {text} (长度={len(text)})")
            # 不自动移除，保留原样（让用户决定）
        
        # 策略3：清理多余的标点（但保留有意义的重复，如"！？"表示疑问+感叹）
        # 只清理完全相同的重复标点
        text = re.sub(r'([。！？])\1+', r'\1', text)  # 多个相同标点合并为一个
        
        # 策略4：优化标点位置（移除标点前的多余空格）
        text = re.sub(r' +([。！？，、])', r'\1', text)
        
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

