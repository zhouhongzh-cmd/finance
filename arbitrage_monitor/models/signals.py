from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

LevelType = Literal["INFO", "WARNING", "CRITICAL"]

@dataclass
class Signal:
    """系统通用报警信号契约"""
    asset: str              # 标的名称/代码
    strategy_name: str      # 策略名称
    level: LevelType        # 报警级别 
    message: str            # 富文本详细报警信息
    timestamp: datetime = field(default_factory=datetime.now)  # 可选自带生成时间
    alert_id: int | None = None  # 入库后记录 ID，用于回写通知状态
