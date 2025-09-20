"""
Модуль управления автоматическими агрегатами TimescaleDB
Решает проблему отсутствия automatic aggregates в системе сбора данных
"""

from .aggregate_manager import AggregateManager

__all__ = ['AggregateManager']