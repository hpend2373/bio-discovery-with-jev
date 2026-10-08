import argparse
import json
import sys
from pathlib import Path

from .runtime import create_plan, run, verify
from .store import connect, counts
from .util import canonical


def main(argv=None):
    parser = argparse.ArgumentParser(description="DEG·메타분석 근거를 Laya/Jev가 전수 검사합니다.")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="입력 검사와 전수 목록 확정; 모델 호출 없음")
    plan.add_argument("--input", required=True)
    plan.add_argument("--profile", required=True)
    plan.add_argument("--out", required=True)
    plan.add_argument("--legacy-deg", action="store_true",
                      help="Explicitly select the historical DEG row/cell/pair × operator contract")
    linkage = commands.add_parser('link-ledger', help='Exact effect-ID source ledger join; preserve inputs and export unmatched/conflict audit')
    for name in ('input','profile','ledger','out'): linkage.add_argument('--'+name, required=True)
    linkage.add_argument('--sheet')
    linkage.add_argument('--ledger-ci-level-percent', action='store_true', help='Explicitly declare ledger CI levels as percentages, independently of the input table')
    linkage.add_argument('--allow-unmatched', action='store_true', help='Keep missing rows unresolved; default requires all input effect IDs')
    execution = commands.add_parser("run", help="전수 모델 검사 실행 또는 재개")
    execution.add_argument("--out", required=True)
    execution.add_argument("--allow-external", action="store_true", help="Jev에 근거 전송을 명시적으로 허용")
    execution.add_argument("--retry-failed", action="store_true", help="원인을 해결한 실패 검사도 재시도")
    for name in ("verify", "status", "report"):
        command = commands.add_parser(name)
        command.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'link-ledger':
            from .ledger_import import prepare_effect_ledger
            result = prepare_effect_ledger(args.input,args.profile,args.ledger,args.out,args.sheet,not args.allow_unmatched,args.ledger_ci_level_percent)
        elif args.command == "plan":
            from .ingest import read_profile
            profile = read_profile(args.profile)
            if profile["domain"] == "deg" and not args.legacy_deg:
                raise ValueError(
                    "새 DEG 작업은 근거 공유 설계를 먼저 적용하세요: docs/efficient-inspection.ko.md. "
                    "범용 카드 실행기는 아직 통합되지 않았습니다. 기존 행·셀·쌍 계약을 "
                    "의도적으로 선택한 경우에만 plan --legacy-deg를 사용하세요.")
            if profile["domain"] != "deg" and args.legacy_deg:
                raise ValueError("--legacy-deg is only valid for DEG profiles")
            result = create_plan(args.input, args.profile, args.out)
        elif args.command == "run":
            result = run(args.out, args.allow_external, args.retry_failed)
        elif args.command == "verify":
            result = verify(args.out)
        elif args.command == "report":
            result = verify(args.out)
            if result["status"] != "verified":
                raise ValueError("검증 실패 결과를 최종 보고서로 내보낼 수 없습니다. 기존 임시 보고서를 확인하세요.")
            from .report import export_report
            result = {"candidates": export_report(args.out), "status": "exported",
                      "candidate_csv": str((Path(args.out) / "candidates.csv").resolve())}
        else:
            db = connect(Path(args.out) / "inspection.sqlite3")
            result = {"manifest": json.loads((Path(args.out) / "manifest.json").read_text()), "counts": counts(db)}
            db.close()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get("status") == "incomplete_or_invalid" else 0
    except KeyboardInterrupt:
        print("중단 상태를 보존했습니다. 같은 run 명령으로 재개할 수 있습니다.", file=sys.stderr)
        return 130
    except (ValueError, RuntimeError, OSError) as exc:
        print("오류: " + str(exc), file=sys.stderr)
        return 1
