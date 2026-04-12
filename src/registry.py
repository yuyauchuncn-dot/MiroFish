#!/usr/bin/env python3
"""MiroFish 报告生成器 — 版本注册表

插件式架构: 每个版本是独立模块，通过统一接口调用。
新增版本只需:
  1. 创建 {version}_generator.py
  2. 在 REGISTRY 中注册

使用:
    from mirofish.registry import get_generator
    gen = get_generator("v4")
    result = gen.generate(transcript="...", title="...", ...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional
from pathlib import Path


@dataclass
class GeneratorInfo:
    """报告生成器元信息"""
    version: str
    name: str
    description: str
    spec_path: str
    factory: Callable  # 返回生成器实例的函数


# ── 版本注册表 ──────────────────────────────────────────────

_REGISTRY: Dict[str, GeneratorInfo] = {}


def register(info: GeneratorInfo):
    """注册一个报告生成器版本"""
    _REGISTRY[info.version] = info


def get_generator(version: str) -> Optional[Any]:
    """获取指定版本的报告生成器实例"""
    if version not in _REGISTRY:
        available = ", ".join(_REGISTRY.keys())
        raise ValueError(f"未知的报告版本: {version}，可用版本: {available}")
    info = _REGISTRY[version]
    return info.factory()


def list_versions() -> Dict[str, str]:
    """列出所有可用的版本"""
    return {v: info.description for v, info in _REGISTRY.items()}


def get_spec_path(version: str) -> str:
    """获取指定版本的 spec 文件路径"""
    if version not in _REGISTRY:
        raise ValueError(f"未知的版本: {version}")
    return _REGISTRY[version].spec_path


# ── 懒加载: 首次使用时才导入具体实现 ──────────────────────

def _make_v3():
    """v3 生成器工厂 (archived)"""
    from v3.v3_generator import V3Generator
    return V3Generator()


def _make_v4():
    """v4 生成器工厂 (多代理辩论 + 预测引擎)"""
    from v4.v4_generator import V4Generator
    return V4Generator()


# ── 注册已实现的版本 ──────────────────────────────────────

_SRC_ROOT = Path(__file__).parent  # src/

register(GeneratorInfo(
    version="v3",
    name="MiroFish v3.0",
    description="经典 6 角色单作者报告 (LLM + Tavily)",
    spec_path=str(_SRC_ROOT / "v3" / "mirofish_v3_spec.md"),
    factory=_make_v3,
))

register(GeneratorInfo(
    version="v4",
    name="MiroFish v4.0",
    description="多代理辩论 + 预测引擎 + Brier Score 校准",
    spec_path=str(_SRC_ROOT / "v4" / "mirofish_v4_spec.md"),
    factory=_make_v4,
))
