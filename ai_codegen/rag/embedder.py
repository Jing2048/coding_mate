"""
嵌入模型模块

提供文本向量化功能。
"""

from typing import List, Optional
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


class Embedder:
    """
    嵌入模型
    
    使用 sentence-transformers 进行文本向量化。
    """
    
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        device: str = "cpu",
        cache_dir: Optional[str] = None
    ):
        """
        初始化嵌入模型
        
        Args:
            model_name: 模型名称
            device: 设备（cpu/cuda）
            cache_dir: 缓存目录
        """
        self.model_name = model_name
        self.device = device
        self.cache_dir = cache_dir
        self._model = None
        self._dimension = None
    
    @property
    def model(self):
        """延迟加载模型"""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
        
        if self._model is None:
            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
                cache_folder=self.cache_dir
            )
        return self._model
    
    def embed(self, text: str) -> List[float]:
        """
        向量化单个文本
        
        Args:
            text: 输入文本
        
        Returns:
            向量列表
        """
        if not text:
            # 返回零向量
            dim = self.get_embedding_dimension()
            return [0.0] * dim
        
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 32,
        show_progress: bool = False
    ) -> List[List[float]]:
        """
        批量向量化
        
        Args:
            texts: 文本列表
            batch_size: 批次大小
            show_progress: 是否显示进度条
        
        Returns:
            向量列表
        """
        if not texts:
            return []
        
        # 过滤空文本
        valid_texts = [t if t else " " for t in texts]
        
        embeddings = self.model.encode(
            valid_texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=show_progress and len(texts) > 100
        )
        return embeddings.tolist()
    
    def get_embedding_dimension(self) -> int:
        """
        获取向量维度
        
        Returns:
            向量维度
        """
        if self._dimension is None:
            # 使用模型获取维度
            test_embedding = self.embed("test")
            self._dimension = len(test_embedding)
        return self._dimension
