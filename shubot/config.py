from dataclasses import dataclass, field


@dataclass
class IntRange:
    """
    最大值与最小值均包含在内。
    """

    min: int
    max: int

    def to_tuple(self) -> tuple[int, int]:
        """转换为 tuple 方便使用"""
        return self.min, self.max


@dataclass
class FloatRange:
    """
    最大值与最小值均包含在内。
    """

    min: float
    max: float

    def to_tuple(self) -> tuple[float, float]:
        """转换为 tuple 方便使用"""
        return self.min, self.max


@dataclass
class TelegramBotConfig:
    """
    Telegram 机器人配置
    """

    token: str
    username: str
    admin_ids: list[int]


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
class RobMessages:
    """打劫模块消息配置"""

    too_weak: str
    """打劫对象太弱的消息"""
    too_strong: str
    """打劫对象太强的消息"""
    escapes: list[str]
    """逃跑成功的消息"""
    tie: str
    """平局的消息"""
    rob_action_descriptions: list[str]
    """被打劫时的描述"""
    steal_complete: list[str]
    """打劫完成的消息"""
    steal_empty: list[str]
    """打劫对象没钱时显示的消息"""
    fight_win: list[str]
    """反抗成功的消息"""
    fight_lose: list[str]
    """反抗失败的消息"""


@dataclass
class RobConfig:
    """打劫模块配置"""

    messages: RobMessages
    """打劫消息配置"""
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
    # 等级: 3, 6, 9, ..., 30
    # 概率: 1.0, 0.9, 0.8, ..., 0.1
    return [BreakThroughConfig(stage, round(1.1 - stage / 30.0, 5)) for stage in range(3, 31, 3)]


def _get_default_cult_stage_names() -> list[str]:
    return [
        "凡夫俗子",
        "后天前期",
        "后天中期",
        "后天后期",
        "先天前期",
        "先天中期",
        "先天后期",
        "练气前期",
        "练气中期",
        "练气后期",
        "筑基前期",
        "筑基中期",
        "筑基后期",
        "金丹前期",
        "金丹中期",
        "金丹后期",
        "元婴前期",
        "元婴中期",
        "元婴后期",
        "化神前期",
        "化神中期",
        "化神后期",
        "炼虚前期",
        "炼虚中期",
        "炼虚后期",
        "合体前期",
        "合体中期",
        "合体后期",
        "大乘前期",
        "大乘中期",
        "大乘后期",
        "渡劫前期",
        "渡劫中期",
        "渡劫后期",
    ]


@dataclass
class CultivationMessages:
    account_missing: str = field(default="❌ 未找到修仙数据")
    level_too_high: str = field(default="❌ 等级满了！")
    insufficient_pts: str = field(default="❌ 积分不足，需要 {cost} 积分，当前积分 {points}，还差 {missing} 积分")
    insufficient_pills: str = field(default="❌ 丹药不足，需要 {cost} 枚，当前 {pills} 枚。")
    breakthrough_success_header: list[str] = field(default_factory=lambda: ["🎉 突破成功！"])
    breakthrough_success: str = field(
        default="{header}\n消耗灵石：{cost}、丹药 {pill_cost} 枚。\n下一境界需要：{next_cost}"
    )

    breakthrough_fail_reason: list[str] = field(default_factory=lambda: ["🎉 突破失败！"])
    breakthrough_fail: str = field(default="{reason}\n消耗灵石：{cost} / 丹药 {pill_cost} 枚，等级保持 {stage} 不变。")


@dataclass
class CultivationConfig:
    major_level_up_chances: list[BreakThroughConfig] = field(default_factory=_default_major_breakthroughs)
    """大突破配置"""
    names: list[str] = field(default_factory=lambda: _get_default_cult_stage_names())
    """境界名称列表"""
    major_pill_cost: int = field(default=10)
    """大突破消耗的突破丹数量"""
    messages: CultivationMessages = field(default_factory=CultivationMessages)
    """修仙模块消息配置"""


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
class LotteryMessages:
    """刮刮乐(乐透)消息配置"""

    game: str
    """游戏开始消息"""
    btn_cost: str
    """抽奖按钮的显示文本模板"""
    owner_mismatch: str
    """拒绝不是本人的点击事件"""
    finish: str
    """抽奖结束消息"""
    insufficient_funds: str
    """余额不足"""
    daily_limit_exceeded: str
    """超过每日抽奖次数限制"""


@dataclass
class LotteryConfig:
    """刮刮乐(乐透)配置"""

    messages: LotteryMessages

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
class LeaderboardMessages:
    """排行榜消息配置"""

    banner: str = field(default="🏯【合书帮·天骄榜】🏯")
    """排行榜标题"""
    entry: str = field(default="{rank} {name} - 等级 {stage}，积分 {points}")
    """排行榜条目模板"""
    separator: str = field(default="\n")
    """排行榜条目分隔符"""
    footer: str = field(default="")
    """排行榜尾部"""


@dataclass
class LeaderboardConfig:
    """排行榜配置"""

    top_count: int = field(default=10)
    """排行榜显示的数量，最大 20"""

    messages: LeaderboardMessages = field(default_factory=LeaderboardMessages)


@dataclass
class MiscMessages:
    """杂项消息配置"""

    user_pts_updated: str = field(default=r"✅ 积分更新: {user}\n🔢 积分更变: `{old}` → `{new}` \(delta\)")
    welcome_member: str = field(default=r"🎉 欢迎 [{name}](tg://user?id={id}) 加入本群！")


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
    """随机事件配置"""
    cultivation: CultivationConfig = field(default_factory=CultivationConfig)
    """修仙模块配置"""
    lottery: LotteryConfig = field(default_factory=LotteryConfig)
    """刮刮乐(乐透)配置"""
    leaderboard: LeaderboardConfig = field(default_factory=LeaderboardConfig)
    """排行榜配置"""
    region_names: dict[str, str] = field(default_factory=dict)
    """意义不明的区域 id 到名称的映射"""
    misc_messages: MiscMessages = field(default_factory=MiscMessages)
    """杂项消息配置"""
