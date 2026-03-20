from abc import ABC, abstractmethod
from typing import List, Any
from models.signals import Signal

class BaseStrategy(ABC):
    """所有套利策略必须继承此抽象基类并实现相关方法"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """返回当前策略的唯一英文缩写或名称"""
        pass

    @abstractmethod
    def evaluate(self, data: Any) -> List[Signal]:
        """
        核心评估入口
        :param data: 具体的模型数据，例如 CBData, FuturesData 等
        :return: 产生的报警信号（没报警返回空列表）
        """
        pass
