# coding=utf-8
"""
归档管理器 - 压缩存储过期数据

功能：
- 将过期的每日 .db 文件压缩归档（按月）
- 归档后删除原始文件，节省磁盘空间
- 支持从归档恢复
- 提供磁盘使用统计
"""

import zipfile
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ArchiveManager:
    """归档管理器"""

    def __init__(self, data_dir: str = "output", timezone: str = "Asia/Shanghai"):
        """
        初始化归档管理器

        Args:
            data_dir: 数据目录路径
            timezone: 时区
        """
        self.data_dir = Path(data_dir)
        self.archive_dir = self.data_dir / "archive"
        self.timezone = timezone

    def archive_old_data(
        self,
        retention_days: int,
        db_types: List[str] = None,
    ) -> Dict[str, int]:
        """
        归档过期数据

        Args:
            retention_days: 保留天数（超过此天数的数据会被归档）
            db_types: 要归档的数据库类型列表，默认 ["news", "rss"]

        Returns:
            归档统计 {"archived": N, "skipped": N, "errors": N}
        """
        if retention_days <= 0:
            return {"archived": 0, "skipped": 0, "errors": 0}

        if db_types is None:
            db_types = ["news", "rss"]

        self.archive_dir.mkdir(parents=True, exist_ok=True)

        cutoff_date = self._get_cutoff_date(retention_days)
        stats = {"archived": 0, "skipped": 0, "errors": 0}

        for db_type in db_types:
            db_dir = self.data_dir / db_type
            if not db_dir.exists():
                continue

            for db_file in sorted(db_dir.glob("*.db")):
                file_date = self._parse_date_from_name(db_file.name)
                if not file_date or file_date >= cutoff_date:
                    stats["skipped"] += 1
                    continue

                try:
                    month_key = file_date.strftime("%Y-%m")
                    archive_path = self.archive_dir / f"{db_type}_{month_key}.zip"

                    self._add_to_archive(archive_path, db_file, db_type)
                    db_file.unlink()
                    stats["archived"] += 1
                    logger.info(f"归档成功: {db_type}/{db_file.name} -> {archive_path.name}")
                except Exception as e:
                    stats["errors"] += 1
                    logger.error(f"归档失败 {db_file}: {e}")

        if stats["archived"] > 0:
            logger.info(
                f"归档完成: {stats['archived']} 个文件, "
                f"跳过 {stats['skipped']}, 失败 {stats['errors']}"
            )

        return stats

    def list_archives(self) -> List[Dict]:
        """
        列出所有归档文件

        Returns:
            归档文件信息列表
        """
        if not self.archive_dir.exists():
            return []

        archives = []
        for zip_file in sorted(self.archive_dir.glob("*.zip")):
            info = self._get_archive_info(zip_file)
            if info:
                archives.append(info)

        return archives

    def get_archive_stats(self) -> Dict:
        """
        获取归档统计信息

        Returns:
            归档统计
        """
        archives = self.list_archives()

        total_size = sum(a.get("file_size", 0) for a in archives)
        total_items = sum(a.get("item_count", 0) for a in archives)

        by_type = {}
        for a in archives:
            db_type = a.get("type", "unknown")
            if db_type not in by_type:
                by_type[db_type] = {"count": 0, "size": 0, "items": 0}
            by_type[db_type]["count"] += 1
            by_type[db_type]["size"] += a.get("file_size", 0)
            by_type[db_type]["items"] += a.get("item_count", 0)

        return {
            "archive_dir": str(self.archive_dir),
            "total_archives": len(archives),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "total_items": total_items,
            "by_type": by_type,
            "archives": archives,
        }

    def restore_archive(
        self,
        archive_name: str,
        target_date: str = None,
    ) -> int:
        """
        从归档恢复数据

        Args:
            archive_name: 归档文件名（如 "news_2026-04.zip"）
            target_date: 恢复指定日期的数据（如 "2026-04-15"），None 表示全部恢复

        Returns:
            恢复的文件数量
        """
        archive_path = self.archive_dir / archive_name
        if not archive_path.exists():
            logger.error(f"归档文件不存在: {archive_path}")
            return 0

        restored = 0
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                for entry in zf.namelist():
                    if not entry.endswith(".db"):
                        continue

                    if target_date and target_date not in entry:
                        continue

                    parts = entry.split("/")
                    if len(parts) >= 2:
                        db_type = parts[0]
                        db_name = parts[1]
                        target_dir = self.data_dir / db_type
                        target_dir.mkdir(parents=True, exist_ok=True)
                        target_path = target_dir / db_name

                        if target_path.exists():
                            logger.warning(f"文件已存在，跳过: {target_path}")
                            continue

                        with zf.open(entry) as src, open(target_path, "wb") as dst:
                            dst.write(src.read())

                        restored += 1
                        logger.info(f"恢复成功: {entry} -> {target_path}")

        except Exception as e:
            logger.error(f"恢复归档失败 {archive_name}: {e}")

        return restored

    def get_disk_usage(self) -> Dict:
        """
        获取磁盘使用统计

        Returns:
            各目录的磁盘使用情况
        """
        usage = {}

        for subdir in ["news", "rss", "txt", "html", "archive"]:
            dir_path = self.data_dir / subdir
            if not dir_path.exists():
                usage[subdir] = {"files": 0, "size_mb": 0}
                continue

            files = list(dir_path.iterdir()) if dir_path.is_dir() else []
            total_size = sum(f.stat().st_size for f in files if f.is_file())

            usage[subdir] = {
                "files": len(files),
                "size_mb": round(total_size / (1024 * 1024), 2),
            }

        total = sum(v["size_mb"] for v in usage.values())
        usage["total_mb"] = round(total, 2)

        return usage

    def _add_to_archive(self, archive_path: Path, db_file: Path, db_type: str):
        """将文件添加到 zip 归档"""
        arcname = f"{db_type}/{db_file.name}"

        with zipfile.ZipFile(archive_path, "a", zipfile.ZIP_DEFLATED) as zf:
            if arcname in zf.namelist():
                logger.warning(f"归档中已存在: {arcname}，覆盖")
                zf.remove(arcname)
            zf.write(db_file, arcname)

    def _get_archive_info(self, zip_path: Path) -> Optional[Dict]:
        """获取归档文件信息"""
        try:
            match = re.match(r"(\w+)_(\d{4}-\d{2})\.zip", zip_path.name)
            if not match:
                return None

            db_type = match.group(1)
            month = match.group(2)

            with zipfile.ZipFile(zip_path, "r") as zf:
                db_files = [n for n in zf.namelist() if n.endswith(".db")]
                item_count = 0
                for entry in db_files:
                    try:
                        item_count += len(zf.namelist())
                    except Exception:
                        pass

                return {
                    "name": zip_path.name,
                    "type": db_type,
                    "month": month,
                    "file_size": zip_path.stat().st_size,
                    "item_count": len(db_files),
                    "entries": db_files,
                }
        except Exception as e:
            logger.error(f"读取归档信息失败 {zip_path}: {e}")
            return None

    def _parse_date_from_name(self, name: str) -> Optional[datetime]:
        """从文件名解析日期"""
        name = name.replace(".db", "")
        try:
            match = re.match(r"(\d{4})-(\d{2})-(\d{2})", name)
            if match:
                import pytz
                return datetime(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                    tzinfo=pytz.timezone(self.timezone),
                )
        except Exception:
            pass
        return None

    def _get_cutoff_date(self, retention_days: int) -> datetime:
        """获取截止日期"""
        import pytz
        from trendradar.utils.time import get_configured_time

        try:
            now = get_configured_time(self.timezone)
        except Exception:
            now = datetime.now(pytz.timezone(self.timezone))

        return now - timedelta(days=retention_days)
