#!/usr/bin/env python3
"""Create a local demonstration account and project; no real paper data is fabricated."""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from research_navigator.db import Database
from research_navigator.models import ResearchProfile, ResearchProject, User
from research_navigator.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("runtime/research_navigator.db"))
    parser.add_argument("--email", default="demo@research-navigator.local")
    parser.add_argument("--password", default="change-this-demo-password")
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    database = Database.from_url(f"sqlite+pysqlite:///{args.database.resolve().as_posix()}")
    database.init()
    with database.session() as session:
        user = session.scalar(select(User).where(User.email == args.email))
        if user is None:
            user = User(
                email=args.email,
                password_hash=hash_password(args.password),
                display_name="Demo Researcher",
            )
            session.add(user)
            session.flush()
            session.add(
                ResearchProfile(
                    user_id=user.id,
                    stage="硕士一年级",
                    major="大数据技术与工程",
                    broad_direction="多变量时序异常检测",
                    keywords_json='["future horizon","alert ranking","false alarms"]',
                    preferences_json='["复现优先"]',
                    excluded_terms_json="[]",
                    compute_constraints="单卡 GPU",
                )
            )
            session.add(
                ResearchProject(
                    user_id=user.id,
                    name="时序异常预警示例项目",
                    broad_direction="未来窗口异常风险排序",
                    description="仅为本地产品流程演示；论文 fixture 均明确标记。",
                )
            )
            session.commit()
    print(f"email={args.email}")
    print("Password was supplied by CLI/default; change it before LAN use.")


if __name__ == "__main__":
    main()
