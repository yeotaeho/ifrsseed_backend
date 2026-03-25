"""임베딩 서비스

텍스트를 벡터 임베딩으로 변환하는 서비스를 제공합니다.
"""
from typing import List, Optional
import numpy as np
from loguru import logger

from backend.core.config.settings import get_settings


class EmbeddingService:
    """임베딩 서비스
    
    BGE-M3 모델을 사용하여 텍스트를 벡터 임베딩으로 변환합니다.
    """
    
    def __init__(self, model_name: Optional[str] = None):
        """임베딩 서비스 초기화
        
        Args:
            model_name: 임베딩 모델 이름 (None이면 설정에서 가져옴)
        """
        self.settings = get_settings()
        self.model_name = model_name or self.settings.embedding_model
        self._embedder = None
        self._model_loaded = False
    
    def _load_model(self):
        """임베딩 모델 로드 (지연 로딩)"""
        if self._model_loaded:
            return
        
        try:
            logger.info(f"🔢 임베딩 모델 로딩 중: {self.model_name}")
            from FlagEmbedding import FlagModel
            self._embedder = FlagModel(self.model_name, use_fp16=True)
            self._model_loaded = True
            logger.info("✅ 임베딩 모델 로드 완료")
        except ImportError:
            logger.error("❌ FlagEmbedding이 설치되지 않았습니다. pip install FlagEmbedding 필요")
            raise
        except Exception as e:
            logger.error(f"❌ 임베딩 모델 로드 실패: {e}")
            raise
    
    def generate_embeddings(
        self,
        texts: List[str],
        normalize: bool = True
    ) -> np.ndarray:
        """임베딩 생성
        
        Args:
            texts: 임베딩할 텍스트 리스트
            normalize: 정규화 여부
        
        Returns:
            임베딩 벡터 배열 (numpy array)
        """
        if not texts:
            return np.array([])
        
        self._load_model()
        
        try:
            logger.debug(f"🔢 {len(texts)}개 텍스트 임베딩 생성 중...")
            # normalize_embeddings 파라미터 제거 (버전 호환성 문제 해결)
            embeddings = self._embedder.encode(texts)
            
            # numpy 배열로 변환 (필요한 경우)
            if not isinstance(embeddings, np.ndarray):
                embeddings = np.array(embeddings)
            
            # 수동 정규화 (필요한 경우)
            if normalize:
                # L2 정규화
                norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
                # 0으로 나누기 방지
                norms = np.where(norms == 0, 1, norms)
                embeddings = embeddings / norms
            
            logger.debug(f"✅ 임베딩 생성 완료: {embeddings.shape}")
            return embeddings
        except Exception as e:
            logger.error(f"❌ 임베딩 생성 실패: {e}")
            raise
    
    def generate_embedding(
        self,
        text: str,
        normalize: bool = True
    ) -> np.ndarray:
        """단일 텍스트 임베딩 생성
        
        Args:
            text: 임베딩할 텍스트
            normalize: 정규화 여부
        
        Returns:
            임베딩 벡터 (1차원 numpy array)
        """
        embeddings = self.generate_embeddings([text], normalize=normalize)
        return embeddings[0]
    
    def get_embedding_dimension(self) -> int:
        """임베딩 차원 반환
        
        Returns:
            임베딩 벡터 차원 (BGE-M3: 1024)
        """
        return 1024  # BGE-M3 고정 차원

