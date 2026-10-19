"""
Command Line Interface (CLI) for budget_app.
Handles argument parsing, interactive user inputs, output formatting,
and dispatches requests to the BudgetService.
"""

import argparse
from datetime import datetime
import os
import sys
from typing import List, Optional

from budget_app.decorators import handle_cli_errors, measure_time
from budget_app.exceptions import ValidationError
from budget_app.formatters import format_currency, format_table
from budget_app.models import validate_date_string, validate_positive_amount, validate_transaction_type
from budget_app.service import BudgetService
from budget_app.storage import StorageManager


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="python -m budget_app",
        description="나만의 용돈 기입장 (Pocket Money & Budget Manager)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        default="./data",
        help="데이터 저장 폴더 경로 (기본값: ./data)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="상세 실행 정보 및 성능 측정 결과 출력",
    )

    subparsers = parser.add_subparsers(dest="command", help="사용 가능한 명령어")

    # 1. add
    add_parser = subparsers.add_parser("add", help="신규 거래 내역 추가 (대화형 입력)")
    add_parser.add_argument("--date", help="거래 날짜 (YYYY-MM-DD)")
    add_parser.add_argument("--type", choices=["income", "expense"], help="거래 타입")
    add_parser.add_argument("--category", help="카테고리명")
    add_parser.add_argument("--amount", type=int, help="금액 (양의 정수)")
    add_parser.add_argument("--memo", default="", help="메모")
    add_parser.add_argument("--tags", help="태그 (쉼표로 구분)")

    # 2. list
    list_parser = subparsers.add_parser("list", help="최신 거래 내역 목록 조회 (스트리밍)")
    list_parser.add_argument("--limit", type=int, default=10, help="조회할 최대 거래 수 (기본값: 10)")
    list_parser.add_argument("--table", action="store_true", help="테이블 포맷으로 정렬 출력")

    # 3. search
    search_parser = subparsers.add_parser("search", help="조건별 거래 내역 검색")
    search_parser.add_argument("--from", dest="from_date", help="시작일 (YYYY-MM-DD)")
    search_parser.add_argument("--to", dest="to_date", help="종료일 (YYYY-MM-DD)")
    search_parser.add_argument("--category", help="카테고리 필터")
    search_parser.add_argument("--type", choices=["income", "expense"], help="타입 필터")
    search_parser.add_argument("--q", help="메모 키워드 검색")
    search_parser.add_argument("--tag", help="태그 필터")
    search_parser.add_argument("--limit", type=int, default=None, help="검색 결과 최대 개수")
    search_parser.add_argument("--table", action="store_true", help="테이블 포맷으로 정렬 출력")

    # 4. summary
    summary_parser = subparsers.add_parser("summary", help="월별 재정 요약 및 예산 현황 리포트")
    summary_parser.add_argument("--month", required=True, help="조회할 연월 (YYYY-MM)")
    summary_parser.add_argument("--top", type=int, default=5, help="지출 상위 카테고리 수 (기본값: 5)")

    # 5. budget
    budget_parser = subparsers.add_parser("budget", help="월별 예산 설정 및 조회")
    budget_sub = budget_parser.add_subparsers(dest="budget_action", help="예산 하위 작업")

    budget_set = budget_sub.add_parser("set", help="월 예산 설정")
    budget_set.add_argument("--month", required=True, help="대상 연월 (YYYY-MM)")
    budget_set.add_argument("--amount", type=int, required=True, help="예산 금액 (원)")

    budget_sub.add_parser("list", help="설정된 전체 월별 예산 목록 조회")

    # 6. category
    cat_parser = subparsers.add_parser("category", help="카테고리 관리")
    cat_sub = cat_parser.add_subparsers(dest="category_action", help="카테고리 하위 작업")

    cat_add = cat_sub.add_parser("add", help="카테고리 추가")
    cat_add.add_argument("name", nargs="?", default=None, help="추가할 카테고리명")

    cat_sub.add_parser("list", help="등록된 카테고리 목록 조회")

    cat_remove = cat_sub.add_parser("remove", help="카테고리 삭제")
    cat_remove.add_argument("name", nargs="?", default=None, help="삭제할 카테고리명")
    cat_remove.add_argument("--replace", help="사용 중인 거래에 대체 적용할 카테고리명")

    # 7. update
    update_parser = subparsers.add_parser("update", help="기존 거래 내역 수정")
    update_parser.add_argument("--id", required=True, help="수정할 거래 ID (예: TX-000001)")
    update_parser.add_argument("--date", help="수정할 날짜 (YYYY-MM-DD)")
    update_parser.add_argument("--type", choices=["income", "expense"], help="수정할 타입")
    update_parser.add_argument("--category", help="수정할 카테고리")
    update_parser.add_argument("--amount", type=int, help="수정할 금액")
    update_parser.add_argument("--memo", help="수정할 메모")
    update_parser.add_argument("--tags", help="수정할 태그 (쉼표 구분)")

    # 8. delete
    delete_parser = subparsers.add_parser("delete", help="거래 내역 삭제")
    delete_parser.add_argument("--id", required=True, help="삭제할 거래 ID (예: TX-000001)")

    # 9. import
    import_parser = subparsers.add_parser("import", help="CSV 파일에서 거래 내역 일괄 가져오기")
    import_parser.add_argument("--from", dest="from_file", required=True, help="가져올 CSV 파일 경로")

    # 10. export
    export_parser = subparsers.add_parser("export", help="거래 내역을 CSV 파일로 내보내기")
    export_parser.add_argument("--out", required=True, help="저장할 CSV 파일 경로")
    export_parser.add_argument("--month", help="내보낼 연월 (YYYY-MM)")
    export_parser.add_argument("--from", dest="from_date", help="시작일 (YYYY-MM-DD)")
    export_parser.add_argument("--to", dest="to_date", help="종료일 (YYYY-MM-DD)")

    # 11. backup (Bonus)
    backup_parser = subparsers.add_parser("backup", help="[보너스] 데이터 전체 백업 zip 파일 생성")
    backup_parser.add_argument("--out", dest="out_dir", help="백업 저장 폴더 경로")

    # 12. recurring (Bonus)
    rec_parser = subparsers.add_parser("recurring", help="[보너스] 매월 반복 거래 설정 및 자동 생성")
    rec_sub = rec_parser.add_subparsers(dest="recurring_action", help="반복 거래 하위 작업")

    rec_add = rec_sub.add_parser("add", help="반복 거래 규칙 추가")
    rec_add.add_argument("--name", help="규칙 이름 (예: 월급, 월세)")
    rec_add.add_argument("--type", choices=["income", "expense"], help="거래 타입")
    rec_add.add_argument("--day", type=int, help="매월 발생 일자 (1-31)")
    rec_add.add_argument("--amount", type=int, help="금액")
    rec_add.add_argument("--category", help="카테고리")
    rec_add.add_argument("--memo", default="", help="메모")

    rec_sub.add_parser("list", help="등록된 반복 규칙 목록 조회")

    rec_apply = rec_sub.add_parser("apply", help="지정 월에 반복 규칙 일괄 적용")
    rec_apply.add_argument("--month", required=True, help="적용할 연월 (YYYY-MM)")

    return parser


def prompt_interactive_input(prompt_text: str, default: Optional[str] = None) -> str:
    """Prompt user for input via terminal, with optional default."""
    if default:
        display = f"{prompt_text} [{default}]: "
    else:
        display = f"{prompt_text}: "
    val = input(display).strip()
    return val if val else (default or "")


def run_add(service: BudgetService, args: argparse.Namespace) -> int:
    """Execute 'add' command."""
    # Check if all options were supplied non-interactively
    if args.date and args.type and args.category and args.amount:
        date_val = args.date
        type_val = args.type
        cat_val = args.category
        amount_val = args.amount
        memo_val = args.memo or ""
        tags_list = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
    else:
        # Interactive mode as specified in mission
        today_str = datetime.now().strftime("%Y-%m-%d")
        while True:
            raw_date = prompt_interactive_input("날짜(YYYY-MM-DD)", default=today_str)
            try:
                date_val = validate_date_string(raw_date)
                break
            except ValidationError as e:
                print(f"[오류] {e.message}", file=sys.stderr)
                if e.hint:
                    print(f"[힌트] {e.hint}", file=sys.stderr)

        while True:
            raw_type = prompt_interactive_input("타입(income/expense)")
            try:
                type_val = validate_transaction_type(raw_type)
                break
            except ValidationError as e:
                print(f"[오류] {e.message}", file=sys.stderr)
                if e.hint:
                    print(f"[힌트] {e.hint}", file=sys.stderr)

        while True:
            raw_cat = prompt_interactive_input("카테고리")
            if not service.storage.categories.exists(raw_cat):
                valid_cats = [c.name for c in service.list_categories()]
                print(f"[오류] 등록되지 않은 카테고리입니다: '{raw_cat}'", file=sys.stderr)
                print(f"[힌트] 등록된 카테고리: {', '.join(valid_cats)}", file=sys.stderr)
                # Ask if user wants to auto-register it
                ans = prompt_interactive_input(f"카테고리 '{raw_cat}'을(를) 새로 등록할까요? (y/N)", default="n")
                if ans.lower() == "y":
                    service.add_category(raw_cat)
                    cat_val = raw_cat
                    print(f"[저장 완료] category={raw_cat}")
                    break
                continue
            cat_val = raw_cat
            break

        while True:
            raw_amount = prompt_interactive_input("금액(양수)")
            try:
                amount_val = validate_positive_amount(raw_amount)
                break
            except ValidationError as e:
                print(f"[오류] {e.message}", file=sys.stderr)
                if e.hint:
                    print(f"[힌트] {e.hint}", file=sys.stderr)

        memo_val = prompt_interactive_input("메모(선택)")
        raw_tags = prompt_interactive_input("태그(쉼표로 구분, 없으면 엔터)")
        tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()]

    tx = service.add_transaction(
        date=date_val,
        tx_type=type_val,
        category=cat_val,
        amount=amount_val,
        memo=memo_val,
        tags=tags_list,
    )
    print(f"[저장 완료] id={tx.id}")
    return 0


def format_tx_line(tx) -> str:
    """Format single transaction in canonical pipe notation matching spec."""
    memo_str = f" {tx.memo}" if tx.memo else ""
    line = f"{tx.id} | {tx.date} | {tx.type:<7} | {tx.category} | {tx.amount} |{memo_str}"
    if tx.tags:
        line += f" | {','.join(tx.tags)}"
    return line


def run_list(service: BudgetService, args: argparse.Namespace) -> int:
    """Execute 'list' command using generator streaming."""
    transactions = list(service.list_transactions(limit=args.limit))
    if not transactions:
        print("[안내] 등록된 거래 내역이 없습니다.")
        return 0

    if args.table:
        headers = ["ID", "날짜", "타입", "카테고리", "금액", "메모", "태그"]
        rows = [
            [
                tx.id,
                tx.date,
                tx.type,
                tx.category,
                format_currency(tx.amount),
                tx.memo,
                ",".join(tx.tags),
            ]
            for tx in transactions
        ]
        alignments = ["left", "center", "center", "left", "right", "left", "left"]
        print(format_table(headers, rows, alignments))
    else:
        for tx in transactions:
            print(format_tx_line(tx))
    return 0


def run_search(service: BudgetService, args: argparse.Namespace) -> int:
    """Execute 'search' command using generator streaming."""
    matching = list(
        service.search_transactions(
            from_date=args.from_date,
            to_date=args.to_date,
            category=args.category,
            tx_type=args.type,
            keyword=args.q,
            tag=args.tag,
            limit=args.limit,
        )
    )
    if not matching:
        print("[안내] 조건에 일치하는 거래 내역이 없습니다.")
        return 0

    if args.table:
        headers = ["ID", "날짜", "타입", "카테고리", "금액", "메모", "태그"]
        rows = [
            [
                tx.id,
                tx.date,
                tx.type,
                tx.category,
                format_currency(tx.amount),
                tx.memo,
                ",".join(tx.tags),
            ]
            for tx in matching
        ]
        alignments = ["left", "center", "center", "left", "right", "left", "left"]
        print(format_table(headers, rows, alignments))
    else:
        for tx in matching:
            print(format_tx_line(tx))
    return 0


def run_summary(service: BudgetService, args: argparse.Namespace) -> int:
    """Execute 'summary' command."""
    summary = service.get_monthly_summary(month=args.month, top_n=args.top)

    if not summary["has_data"]:
        print(f"[안내] {args.month} 월의 거래 데이터가 없습니다.")
        return 0

    print(f"총 수입: {summary['total_income']}원")
    print(f"총 지출: {summary['total_expense']}원")
    print(f"잔액: {summary['balance']}원")

    if summary["budget"]:
        usage = summary["budget_usage_rate"]
        print(f"예산: {summary['budget'].amount}원 (사용률 {usage:.1f}%)")
        if summary["is_over_budget"]:
            print(f"[경고] 예산을 {summary['over_amount']:,}원 초과했습니다! (사용률 {usage:.1f}%)")

    top_cats = summary["top_categories"]
    if top_cats:
        print(f"\n지출 TOP {len(top_cats)}")
        for idx, (cat, amt) in enumerate(top_cats, start=1):
            print(f"{idx}) {cat} {amt}원")

    return 0


def run_budget(service: BudgetService, args: argparse.Namespace) -> int:
    """Execute 'budget' subcommand."""
    action = args.budget_action
    if action == "set":
        b = service.set_budget(month=args.month, amount=args.amount)
        print(f"[저장 완료] {b.month} 예산 {b.amount}원")
        return 0
    elif action == "list":
        budgets = service.list_budgets()
        if not budgets:
            print("[안내] 설정된 예산이 없습니다.")
            return 0
        headers = ["연월", "예산 금액", "등록일시"]
        rows = [[b.month, format_currency(b.amount), b.created_at[:19]] for b in budgets]
        print(format_table(headers, rows, ["center", "right", "center"]))
        return 0
    else:
        print("[오류] budget 작업(set/list)을 지정해주세요.", file=sys.stderr)
        print("[힌트] 예: python -m budget_app budget set --month 2024-01 --amount 500000", file=sys.stderr)
        return 1


def run_category(service: BudgetService, args: argparse.Namespace) -> int:
    """Execute 'category' subcommand."""
    action = args.category_action
    if action == "add":
        name = args.name
        if not name:
            name = prompt_interactive_input("카테고리명")
        cat = service.add_category(name)
        print(f"[저장 완료] category={cat.name}")
        return 0
    elif action == "list":
        cats = service.list_categories()
        if not cats:
            print("[안내] 등록된 카테고리가 없습니다.")
            return 0
        for c in cats:
            print(f"- {c.name}")
        return 0
    elif action == "remove":
        name = args.name
        if not name:
            name = prompt_interactive_input("삭제할 카테고리명")
        service.remove_category(name, replacement=args.replace)
        if args.replace:
            print(f"[삭제 완료] category={name} (기존 거래는 '{args.replace}'(으)로 대체 반영됨)")
        else:
            print(f"[삭제 완료] category={name}")
        return 0
    else:
        print("[오류] category 작업(add/list/remove)을 지정해주세요.", file=sys.stderr)
        print("[힌트] 예: python -m budget_app category list", file=sys.stderr)
        return 1


def run_update(service: BudgetService, args: argparse.Namespace) -> int:
    """
    Execute 'update' command.
    Supports option-based update, or interactive prompt if options are omitted.
    """
    tx_id = args.id
    existing = service.storage.transactions.get_by_id(tx_id)
    if not existing:
        raise ValidationError(
            f"ID '{tx_id}'에 해당하는 거래를 찾을 수 없습니다.",
            hint="list 명령으로 존재하는 거래 ID를 확인해주세요.",
        )

    # If no update flags passed, enter interactive mode for fields
    has_options = any(
        [args.date, args.type, args.category, args.amount is not None, args.memo is not None, args.tags]
    )
    if not has_options:
        print(f"[거래 수정 대화형 모드] 현재 데이터: {format_tx_line(existing)}")
        print("수정하지 않고 유지하려면 엔터를 입력하세요.")
        date_in = prompt_interactive_input("날짜(YYYY-MM-DD)", default=existing.date)
        type_in = prompt_interactive_input("타입(income/expense)", default=existing.type)
        cat_in = prompt_interactive_input("카테고리", default=existing.category)
        amt_in = prompt_interactive_input("금액", default=str(existing.amount))
        memo_in = prompt_interactive_input("메모", default=existing.memo)
        tags_in = prompt_interactive_input("태그(쉼표 구분)", default=",".join(existing.tags))

        updated = service.update_transaction(
            tx_id=tx_id,
            date=date_in,
            tx_type=type_in,
            category=cat_in,
            amount=int(amt_in),
            memo=memo_in,
            tags=[t.strip() for t in tags_in.split(",") if t.strip()],
        )
    else:
        tags_list = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None
        updated = service.update_transaction(
            tx_id=tx_id,
            date=args.date,
            tx_type=args.type,
            category=args.category,
            amount=args.amount,
            memo=args.memo,
            tags=tags_list,
        )

    print(f"[수정 완료] id={updated.id} | {updated.date} | {updated.type} | {updated.category} | {updated.amount}원")
    return 0


def run_delete(service: BudgetService, args: argparse.Namespace) -> int:
    """Execute 'delete' command."""
    service.delete_transaction(args.id)
    print(f"[삭제 완료] id={args.id} 거래가 정상적으로 삭제되었습니다.")
    return 0


def run_import(service: BudgetService, args: argparse.Namespace) -> int:
    """Execute 'import' command."""
    imported, skipped = service.import_csv(args.from_file)
    print(f"[완료] imported={imported}, skipped={skipped}")
    return 0


def run_export(service: BudgetService, args: argparse.Namespace) -> int:
    """Execute 'export' command."""
    count = service.export_csv(
        out_path=args.out,
        month=args.month,
        from_date=args.from_date,
        to_date=args.to_date,
    )
    print(f"[완료] {os.path.basename(args.out)} ({count} records)")
    return 0


def run_backup(service: BudgetService, args: argparse.Namespace) -> int:
    """Execute 'backup' command (Bonus)."""
    zip_path = service.create_backup(target_dir=args.out_dir)
    print(f"[완료] 백업 파일 생성: {zip_path}")
    return 0


def run_recurring(service: BudgetService, args: argparse.Namespace) -> int:
    """Execute 'recurring' command (Bonus)."""
    action = args.recurring_action
    if action == "add":
        name = args.name or prompt_interactive_input("규칙명(예: 월세, 통신비)")
        tx_type = args.type or prompt_interactive_input("타입(income/expense)")
        day = args.day or int(prompt_interactive_input("매월 발생일(1-31)"))
        amount = args.amount or int(prompt_interactive_input("금액"))
        cat = args.category or prompt_interactive_input("카테고리")
        memo = args.memo or prompt_interactive_input("메모(선택)", default="")
        rule = service.add_recurring_rule(
            name=name,
            tx_type=tx_type,
            day_of_month=day,
            amount=amount,
            category=cat,
            memo=memo,
        )
        print(f"[저장 완료] id={rule.id} name={rule.name} (매월 {rule.day_of_month}일 {rule.amount}원)")
        return 0
    elif action == "list":
        rules = service.list_recurring_rules()
        if not rules:
            print("[안내] 등록된 반복 규칙이 없습니다.")
            return 0
        headers = ["ID", "규칙명", "타입", "발생일", "카테고리", "금액", "메모"]
        rows = [
            [
                r.id,
                r.name,
                r.type,
                f"매월 {r.day_of_month}일",
                r.category,
                format_currency(r.amount),
                r.memo,
            ]
            for r in rules
        ]
        print(format_table(headers, rows))
        return 0
    elif action == "apply":
        count = service.apply_recurring(month=args.month)
        print(f"[완료] {args.month} 월에 {count}건의 반복 거래가 자동 등록되었습니다.")
        return 0
    else:
        print("[오류] recurring 작업(add/list/apply)을 지정해주세요.", file=sys.stderr)
        print("[힌트] 예: python -m budget_app recurring apply --month 2024-01", file=sys.stderr)
        return 1


@handle_cli_errors
@measure_time
def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.verbose:
        os.environ["BUDGET_APP_VERBOSE"] = "1"

    storage_manager = StorageManager(data_dir=args.data_dir)
    service = BudgetService(storage_manager=storage_manager)

    commands = {
        "add": run_add,
        "list": run_list,
        "search": run_search,
        "summary": run_summary,
        "budget": run_budget,
        "category": run_category,
        "update": run_update,
        "delete": run_delete,
        "import": run_import,
        "export": run_export,
        "backup": run_backup,
        "recurring": run_recurring,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(service, args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
