"""
Скрипт для синхронизации данных сотрудников из Platonus
Запуск: python sync_employees.py
"""

import asyncio
import sys
from app.core.database import SessionLocal
from app.services.platonus_sync import PlatonusSyncService
import logging

# Настроить логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """Главная функция"""
    logger.info("=" * 80)
    logger.info("ЗАПУСК СИНХРОНИЗАЦИИ СОТРУДНИКОВ ИЗ PLATONUS")
    logger.info("=" * 80)

    try:
        async with SessionLocal() as db:
            service = PlatonusSyncService(db)

            # Выполнить синхронизацию
            result = await service.sync_employees()

            # Вывести результаты
            logger.info("\n" + "=" * 80)
            logger.info("РЕЗУЛЬТАТЫ СИНХРОНИЗАЦИИ")
            logger.info("=" * 80)
            logger.info(f"Статус: {result['status']}")
            logger.info(f"Всего сотрудников в HikCentral: {result.get('total', 0)}")
            logger.info(f"Синхронизировано: {result.get('synced', 0)}")
            logger.info(f"Не найдено в Platonus: {result.get('not_found', 0)}")
            logger.info(f"Ошибок: {result.get('errors', 0)}")

            # Получить статистику
            logger.info("\n" + "=" * 80)
            logger.info("СТАТИСТИКА КЕША")
            logger.info("=" * 80)

            stats = await service.get_sync_stats()
            logger.info(f"Всего в кеше: {stats['total_employees']}")
            logger.info(f"Последняя синхронизация: {stats['last_sync']}")

            logger.info("\nПо типам должностей:")
            for pos_type, count in stats.get('by_position_type', {}).items():
                logger.info(f"  {pos_type}: {count}")

            logger.info("\nПо факультетам (топ-10):")
            for idx, (faculty, count) in enumerate(
                list(stats.get('by_faculty', {}).items())[:10], 1
            ):
                logger.info(f"  {idx}. {faculty}: {count}")

            logger.info("\n" + "=" * 80)
            logger.info("СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА УСПЕШНО")
            logger.info("=" * 80)

            return 0

    except Exception as e:
        logger.error(f"\n❌ ОШИБКА СИНХРОНИЗАЦИИ: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Прервано пользователем")
        sys.exit(0)
