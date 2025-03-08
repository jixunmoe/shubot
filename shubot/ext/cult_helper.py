from functools import lru_cache

from shubot.config import Config


class CultivationHelperMixin:
    _config: Config

    @property
    @lru_cache
    def max_cult_stage(self) -> int:
        """获取最大境界"""
        return len(self._config.cultivation.names) - 1

    @lru_cache
    def _get_cult_stage_name(self, stage: int) -> str:
        """获取境界名称"""
        return self._config.cultivation.names[stage] if 0 <= stage <= self.max_cult_stage else "未知境界"
