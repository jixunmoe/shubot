from dataclasses import dataclass, field


@dataclass
class IntRange:
    """
    最大值与最小值均包含在内。
    """
    min: int
    max: int


@dataclass
class FloatRange:
    """
    最大值与最小值均包含在内。
    """
    min: float
    max: float


@dataclass
class TelegramBotConfig:
    """
    Telegram 机器人配置
    """
    token: str
    username: str
    admin_ids: list[str]


@dataclass
class DatabaseConfig:
    """数据库配置 (MySQL / MariaDB)"""
    host: str = field(default="127.0.0.1")
    port: int = field(default=3306)
    db: str = field(default="shubot")
    user: str = field(default="shubot")
    password: str = field(default="shubot")


@dataclass
class BookRepoConfig:
    """书库信息"""
    url: str
    username: str
    password: str
    notice: str


@dataclass
class BookConfig:
    """书籍模块配置"""
    download_path: str
    """下载路径"""
    book_repo: BookRepoConfig
    """书库配置"""
    allowed_extensions: list[str] = field(default_factory=lambda: [".txt", ".epub"])
    """允许的文件扩展名"""
    points_per_book: int = field(default=10)
    """贡献一本书得到的点数"""


@dataclass
class SlaveRulesConfig:
    """猫娘模块配置"""
    init_phrase: str = field(default="见过主人，喵~")
    daily_phrase: str = field(default="喵")
    max_retry: int = field(default=3)


@dataclass
class RobConfig:
    """打劫模块配置"""

    daily_limit: int = field(default=5)
    """每日打劫次数限制"""
    escape_chance: float = field(default=0.2)
    """逃跑成功的概率"""
    stage_bonus: int = field(default=3)
    """高等级用户的骰子点数加成"""
    penalty_ratio: FloatRange = field(default_factory=lambda: FloatRange(0.1, 0.3))
    """失败时的惩罚比例，例如 min=0.1, max=0.3 表示惩罚会扣除 10% ~ 30% 的点数"""
    cooldown: int = field(default=60)
    """打劫冷却时间，单位为秒"""
    dice_range: IntRange = field(default_factory=lambda: IntRange(1, 6))
    """骰子点数范围"""


@dataclass
class GangConfig:
    """帮派模块配置"""
    base_donation: int = field(default=100)
    """上供基础点数"""
    reset_hour: int = field(default=21)
    """每日帮派活动结算活动时间（小时）"""
    reset_minute: int = field(default=33)
    """每日帮派活动结算活动时间（分钟）"""


@dataclass
class RandomEventConfig:
    """随机事件配置"""
    id: str
    """事件 ID"""
    name: str
    """事件名称"""
    chance: float
    """事件发生概率，取 0-1 之间的小数"""


@dataclass
class BreakThroughConfig:
    """突破事件配置"""
    level: int
    """顿悟时的等级"""
    chance: float
    """突破提升概率"""


def _default_major_breakthroughs() -> list[BreakThroughConfig]:
    # 等级: 3, 6, 9, ...
    # 概率: 1.0, 0.9, 0.8, ...
    return [BreakThroughConfig(i * 3 + 3, 1.0 - 0.1 * i) for i in range(10)]


@dataclass
class LotteryPrize:
    """刮刮乐(乐透)奖品配置"""

    cost: int
    """抽奖消耗的点数"""
    prize: int
    """中奖时获得的点数"""


def _default_lottery_prizes() -> list[LotteryPrize]:
    return [LotteryPrize(cost, cost * 10) for cost in (3, 10, 50)]


@dataclass
class LotteryConfig:
    """刮刮乐(乐透)配置"""

    chance: float = field(default=0.1)
    """中奖概率"""
    daily_limit: int = field(default=5)
    """每日抽奖次数限制"""
    number_range: IntRange = field(default_factory=lambda: IntRange(1, 20))
    """抽奖数字范围"""
    select_count: int = field(default=5)
    """抽奖数字的数量"""
    prizes: list[LotteryPrize] = field(default_factory=_default_lottery_prizes)
    """奖品和价格列表"""


@dataclass
class Config:
    """总配置文件对象"""

    telegram: TelegramBotConfig
    """Telegram 机器人配置"""
    db: DatabaseConfig
    """数据库配置"""
    book: BookConfig
    """书籍模块配置"""
    slave_rules: SlaveRulesConfig = field(default_factory=SlaveRulesConfig)
    """猫娘模块配置"""
    rob: RobConfig = field(default_factory=RobConfig)
    """打劫模块配置"""
    gang: GangConfig = field(default_factory=GangConfig)
    """帮派模块配置"""
    random_events: list[RandomEventConfig] = field(default_factory=list)
    cultivation: list[str] = field(default_factory=list)
    """头衔列表"""
    major_breakthroughs: list[BreakThroughConfig] = field(default_factory=_default_major_breakthroughs)
    """大突破配置"""
    lottery: LotteryConfig = field(default_factory=LotteryConfig)
    """刮刮乐(乐透)配置"""
    region_names: dict[str, str] = field(default_factory=dict)
    """意义不明的区域 id 到名称的映射"""
