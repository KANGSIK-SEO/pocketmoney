# 💰 나만의 용돈 기입장 (pocketmoney)

> **"작은 서비스란 기능이 많은 것이 아니라, 예외 상황에서도 데이터가 안전하고 유지보수 가능한 구조를 갖춘 것"**

`pocketmoney`는 Python 3.10+ 표준 라이브러리만을 사용하여 구현된 파일 입출력 기반의 고신뢰성 콘솔 가계부 애플리케이션입니다.  
수입/지출 내역 CRUD, 조건별 검색, 월별 통계 및 예산 초과 경고, 카테고리 무결성 관리, CSV 가져오기/내보내기뿐만 아니라 **제너레이터 기반 역방향 스트리밍**, **원자적 파일 교체 트랜잭션**, **데코레이터 기반 관심사 분리**, **CJK 폭 보정 콘솔 테이블 정렬**까지 갖춘 완성형 아키텍처를 제공합니다.

---

## 📑 목차
1. [시스템 아키텍처 및 모듈 구성](#-시스템-아키텍처-및-모듈-구성)
2. [저장 파일 위치 및 포맷 규격](#-저장-파일-위치-및-포맷-규격)
3. [핵심 기술적 설계 및 원리](#-핵심-기술적-설계-및-원리)
   - [1) yield 기반 제너레이터 스트리밍](#1-yield-기반-제너레이터-스트리밍)
   - [2) 데코레이터 기반 공통 관심사 분리](#2-데코레이터-기반-공통-관심사-분리)
   - [3) 파일 I/O 원자성(Atomicity) 보장](#3-파일-io-원자성atomicity-보장)
   - [4) 엄격한 타입 힌트와 입력 검증 계약](#4-엄격한-타입-힌트와-입력-검증-계약)
4. [기능별 명령어 사용법 및 실행 예시](#-기능별-명령어-사용법-및-실행-예시)
   - [1. add (거래 추가 - 대화형)](#1-add-거래-추가---대화형)
   - [2. list (거래 목록 조회 - 스트리밍)](#2-list-거래-목록-조회---스트리밍)
   - [3. search (조건별 거래 검색)](#3-search-조건별-거래-검색)
   - [4. summary (월별 요약 및 예산 모니터링)](#4-summary-월별-요약-및-예산-모니터링)
   - [5. budget (월별 예산 설정/조회)](#5-budget-월별-예산-설정조회)
   - [6. category (카테고리 관리 및 참조 무결성)](#6-category-카테고리-관리-및-참조-무결성)
   - [7. update (거래 수정 - 옵션/대화형 고정)](#7-update-거래-수정---옵션대화형-고정)
   - [8. delete (거래 삭제 - 원자적 제거)](#8-delete-거래-삭제---원자적-제거)
   - [9. import / export (CSV 입출력)](#9-import--export-csv-입출력)
5. [보너스 기능 (Bonus Features)](#-보너스-기능-bonus-features)
   - [백업 (backup)](#백업-backup)
   - [매월 반복 내역 자동 생성 (recurring)](#매월-반복-내역-자동-생성-recurring)
   - [한글 너비 보정 테이블 포맷터 (--table)](#한글-너비-보정-테이블-포맷터---table)
6. [CSV Import / Export 규격 명세](#-csv-import--export-규격-명세)
7. [테스트 실행 방법](#-테스트-실행-방법)

---

## 🏛 시스템 아키텍처 및 모듈 구성

본 애플리케이션은 계층화 아키텍처(Layered Architecture)를 준수하여 책임을 명확히 격리했습니다.

```
pocketmoney/
├── budget_app/
│   ├── __init__.py          # 패키지 메타데이터
│   ├── __main__.py          # python -m budget_app 실행 진입점
│   ├── models.py            # 데이터 모델 (Transaction, Category, Budget, RecurringRule)
│   ├── storage.py           # 파일 영구 저장소 및 제너레이터 스트리밍 I/O
│   ├── service.py           # 핵심 비즈니스 로직 및 유효성 검증 계층
│   ├── cli.py               # argparse 기반 CLI 디스패처 및 대화형 UX
│   ├── decorators.py        # 예외 처리, 시간 측정, 감사 로깅 데코레이터
│   ├── formatters.py        # 터미널 한글 CJK 문자 폭 계산 및 테이블 포맷터
│   └── exceptions.py        # 원인 및 해결 힌트가 포함된 도메인 커스텀 예외
├── tests/                   # unittest 표준 테스트 스위트 (100% 통과)
│   ├── test_models.py
│   ├── test_storage.py
│   ├── test_service.py
│   ├── test_decorators.py
│   ├── test_formatters.py
│   └── test_cli.py
└── data/                    # 영구 저장 파일 디렉터리 (기본값: ./data)
    ├── transactions.jsonl   # 거래 내역 데이터 (JSONL)
    ├── categories.jsonl     # 등록된 카테고리 데이터 (JSONL)
    ├── budgets.jsonl        # 월별 예산 데이터 (JSONL)
    └── recurring.jsonl      # 반복 거래 규칙 데이터 (JSONL)
```

### 각 계층의 책임과 역할
- **CLI (`cli.py`)**: 사용자 인자 파싱(`argparse`), 대화형 프롬프트(`input()`), 출력 서식 지정 및 비즈니스 서비스 호출 담당.
- **Service (`service.py`)**: 거래 CRUD, 검색 조건 필터링, 월별 결산, 카테고리 참조 무결성 검증, CSV 가져오기/내보내기 등 도메인 규칙 총괄.
- **Storage (`storage.py`)**: 디렉터리/파일 자동 생성, JSONL 파일 스트리밍 파싱(`yield`), 임시 파일을 통한 원자적 쓰기(`os.replace`) 처리.
- **Models (`models.py`)**: `dataclass` 기반의 불변/유효성 보장 엔티티 정의 및 직렬화/역직렬화 메서드 제공.
- **Decorators (`decorators.py`)**: CLI 진입점의 오류 가로채기(스택트레이스 방지, 사용자 힌트 출력, 적절한 exit code 반환) 및 성능 측정.

---

## 📂 저장 파일 위치 및 포맷 규격

데이터는 프로그램 종료 후에도 영구 보존되도록 **JSONL (JSON Lines)** 형식으로 분리 저장됩니다.

| 파일명 | 기본 경로 | 저장 형식 | 설명 |
| :--- | :--- | :--- | :--- |
| **`transactions.jsonl`** | `./data/transactions.jsonl` | JSONL | 개별 거래 내역 (ID, 날짜, 타입, 카테고리, 금액, 메모, 태그) |
| **`categories.jsonl`** | `./data/categories.jsonl` | JSONL | 시스템에 등록된 카테고리 목록 (기본 카테고리 자동 초기화) |
| **`budgets.jsonl`** | `./data/budgets.jsonl` | JSONL | 연월(`YYYY-MM`)별 지출 예산 한도 설정값 |
| **`recurring.jsonl`** | `./data/recurring.jsonl` | JSONL | [보너스] 매월 정기 발생하는 반복 거래 규칙 |

- 기본 저장 위치는 `./data`이며, `--data-dir <경로>` 옵션을 통해 임의의 디렉터리로 변경할 수 있습니다.
- 저장 파일이 없는 최초 실행 시 필요한 디렉터리와 파일을 자동으로 생성하며, 카테고리 파일이 비어있는 경우 필수 기본 카테고리(`food`, `transport`, `rent`, `salary`, `식비`, `교통` 등)를 자동 초기화합니다 (**안 A 채택**).

---

## 💡 핵심 기술적 설계 및 원리

### 1) yield 기반 제너레이터 스트리밍
- **도입 이유**: 대용량 파일(수십만~수백만 줄)을 `f.readlines()`나 `json.load()`로 메모리에 한 번에 올리면 O(N)의 메모리 폭증과 불필요한 I/O 지연이 발생합니다.
- **동작 방식**: 
  - `storage.py`의 `reverse_readline()`은 파일의 끝(EOF)에서부터 64KB 블록 단위로 역방향 탐색하여 줄바꿈(`\n`) 기준으로 한 줄씩 디코딩하고 `yield`로 방출합니다.
  - 최신순 조회가 필요한 `list`와 `search`는 필요한 개수(`--limit N`)만큼만 스트림에서 소비하고 즉시 중단되므로, 데이터 파일 크기에 무관하게 **O(1)의 메모리 복잡도**와 밀리초 단위의 빠른 응답성을 보장합니다.

### 2) 데코레이터 기반 공통 관심사 분리
- **`@handle_cli_errors`**: 모든 CLI 실행 함수에 적용되어 `BudgetAppException` 및 `KeyboardInterrupt`를 포착합니다.
  - 사용자에게 흉측한 파이썬 스택트레이스를 노출하지 않고, 정제된 `[오류]` 메시지와 해결 가이드인 `[힌트]`를 출력합니다.
  - 정상 종료 시 `exit code 0`, 도메인/유효성 오류 시 `exit code 1`, 사용자 중단 시 `exit code 130`을 명확히 반환합니다.
- **`@measure_time`**: `--verbose` 플래그 활성화 시 실행 경과 시간을 마이크로초/밀리초 단위로 측정하여 성능 병목 여부를 확인할 수 있습니다.

### 3) 파일 I/O 원자성(Atomicity) 보장
- **문제점**: 파일 기반 저장소에서 `update`나 `delete` 시 대상 파일을 직접 덮어쓰다 프로세스가 강제 종료되면 파일이 손상되거나 빈 파일로 남는 치명적인 데이터 유실이 발생할 수 있습니다.
- **해결책 (`atomic_write_jsonl`)**:
  1. 대상 파일과 동일한 디렉터리에 `tempfile.mkstemp`로 임시 파일을 생성합니다.
  2. 새로운 데이터를 임시 파일에 모두 기록한 후 `f.flush()` 및 OS 버퍼를 디스크에 강제 동기화하는 `os.fsync(f.fileno())`를 호출합니다.
  3. POSIX 원자적 연산인 `os.replace(temp_path, target_path)`를 호출하여 원본 파일을 단 한 번의 inode 교체로 안전하게 갱신합니다.

### 4) 엄격한 타입 힌트와 입력 검증 계약
- 함수 파라미터와 반환값에 `Optional`, `List`, `Iterator`, `Dict`, `Tuple` 등 표준 타입 힌트를 전면 적용했습니다.
- 데이터 생성 단계(`models.py`)에서 날짜 정규식 및 캘린더 일자 검증(`validate_date_string`), 양수 정수 검증(`validate_positive_amount`), 거래 유형 검증(`validate_transaction_type`)을 사전 강제하여 잘못된 데이터의 도메인 유입을 원천 차단합니다.

---

## 🚀 기능별 명령어 사용법 및 실행 예시

모든 명령은 리눅스 표준인 `--` 옵션을 사용하며, `--help`로 상세 도움말을 확인할 수 있습니다.

```bash
python -m budget_app --help
```

### 1. add (거래 추가 - 대화형)
프롬프트를 통해 순차적으로 입력받으며, 잘못된 입력 시 원인과 힌트를 제공하고 올바른 값 입력을 유도합니다.

```bash
$ python -m budget_app add
날짜(YYYY-MM-DD): 2024-01-15
타입(income/expense): expense
카테고리: food
금액(양수): 15000
메모(선택): 점심
태그(쉼표로 구분, 없으면 엔터): meal
[저장 완료] id=TX-000001
```

> **비대화형 옵션 모드 지원**: 자동화 스크립트 실행을 위해 옵션 전달도 가능합니다:
> `python -m budget_app add --date 2024-01-15 --type expense --category food --amount 15000 --memo 점심`

### 2. list (거래 목록 조회 - 스트리밍)
최신 거래부터 역순으로 스트리밍 출력합니다.

```bash
$ python -m budget_app list --limit 3
TX-000003 | 2024-01-15 | expense | food    | 15000 | 점심 | meal
TX-000002 | 2024-01-14 | income  | salary  | 3000000 | |
TX-000001 | 2024-01-12 | expense | transport | 20000 | |
```

> `--table` 옵션을 주면 정렬된 콘솔 테이블로 출력됩니다.

### 3. search (조건별 거래 검색)
기간, 카테고리, 수입/지출 타입, 메모 키워드, 태그 등 다중 조건 검색을 지원합니다.

```bash
$ python -m budget_app search --category food --from 2024-01-01 --to 2024-01-31
TX-000003 | 2024-01-15 | expense | food    | 15000 | 점심 | meal
```

### 4. summary (월별 요약 및 예산 모니터링)
지정 연월의 총수입, 총지출, 잔액 및 지출 상위 TOP N 카테고리를 집계합니다. 예산이 설정된 경우 사용률과 초과 경고를 표시합니다.

```bash
$ python -m budget_app summary --month 2024-01 --top 3
총 수입: 3000000원
총 지출: 215000원
잔액: 2785000원
예산: 500000원 (사용률 43.0%)

지출 TOP 3
1) rent 150000원
2) food 45000원
3) transport 20000원
```

만약 예산을 초과한 경우 다음과 같이 명확한 경고가 함께 출력됩니다:
```
[경고] 예산을 15,000원 초과했습니다! (사용률 107.5%)
```

### 5. budget (월별 예산 설정/조회)
특정 월의 지출 예산 한도를 영구 저장합니다.

```bash
$ python -m budget_app budget set --month 2024-01 --amount 500000
[저장 완료] 2024-01 예산 500000원

$ python -m budget_app budget list
+---------+-------------+---------------------+
|  연월   |  예산 금액  |      등록일시       |
+---------+-------------+---------------------+
| 2024-01 |   500,000원 | 2024-01-10T10:00:00 |
+---------+-------------+---------------------+
```

### 6. category (카테고리 관리 및 참조 무결성)
카테고리 추가, 목록 조회 및 삭제를 지원합니다.  
**참조 무결성 보장**: 거래 내역에서 사용 중인 카테고리를 삭제하려고 하면 삭제를 차단하거나 `--replace` 옵션으로 일괄 대체를 요구합니다.

```bash
# 카테고리 추가
$ python -m budget_app category add food
[저장 완료] category=food

# 카테고리 목록
$ python -m budget_app category list
- food
- transport
- rent

# 사용 중인 카테고리 삭제 시도 (보호)
$ python -m budget_app category remove food
[오류] 카테고리 'food'은(는) 현재 5건의 거래 내역에서 사용 중입니다.
[힌트] 해당 거래들을 먼저 수정/삭제하거나, --replace <새카테고리> 옵션을 사용해 대체하세요.

# 대체 카테고리를 지정하여 안전한 삭제
$ python -m budget_app category remove food --replace etc
[삭제 완료] category=food (기존 거래는 'etc'(으)로 대체 반영됨)
```

### 7. update (거래 수정 - 옵션/대화형 고정)
본 애플리케이션은 요구사항에 따라 **옵션 기반 수정**을 기본 표준으로 채택하며, 필드 인자가 생략되었을 경우 **대화형 필드 재입력 모드**를 유연하게 지원합니다.

```bash
# 옵션 기반 수정
$ python -m budget_app update --id TX-000001 --amount 18000 --memo "점심(특식)"
[수정 완료] id=TX-000001 | 2024-01-15 | expense | food | 18000원
```

### 8. delete (거래 삭제 - 원자적 제거)
거래 ID를 지정하여 원자적으로 안전하게 삭제합니다.

```bash
$ python -m budget_app delete --id TX-000001
[삭제 완료] id=TX-000001 거래가 정상적으로 삭제되었습니다.
```

### 9. import / export (CSV 입출력)

```bash
# CSV 거래 내역 일괄 가져오기
$ python -m budget_app import --from sample.csv
[완료] imported=5, skipped=0

# 조건부 CSV 내보내기 (특정 월 또는 기간 필수)
$ python -m budget_app export --out export_2024_01.csv --month 2024-01
[완료] export_2024_01.csv (12 records)

$ python -m budget_app export --out export_range.csv --from 2024-01-01 --to 2024-01-15
[완료] export_range.csv (8 records)
```

---

## 🎁 보너스 기능 (Bonus Features)

### 백업 (backup)
운영 안정성을 위해 현재 데이터 디렉터리(`transactions`, `categories`, `budgets` 등) 전체를 타임스탬프 기반 ZIP 압축 파일로 안전하게 백업합니다.

```bash
$ python -m budget_app backup
[완료] 백업 파일 생성: /path/to/backups/pocketmoney_backup_20261019_211500.zip
```

### 매월 반복 내역 자동 생성 (recurring)
월급, 월세, 통신비 등 매달 정기적으로 발생하는 내역을 등록해 두고 지정된 월에 일괄 자동 생성합니다. 윤년 및 월말 일자(28, 29, 30, 31일)는 안전하게 클램핑 보정됩니다.

```bash
# 반복 규칙 등록
$ python -m budget_app recurring add --name "월세" --type expense --day 25 --amount 500000 --category rent --memo "매월 월세"
[저장 완료] id=REC-0001 name=월세 (매월 25일 500000원)

# 반복 규칙 목록 조회
$ python -m budget_app recurring list

# 지정된 월에 자동 생성 반영
$ python -m budget_app recurring apply --month 2024-02
[완료] 2024-02 월에 1건의 반복 거래가 자동 등록되었습니다.
```

### 한글 너비 보정 테이블 포맷터 (--table)
외부 의존성 없이 `unicodedata.east_asian_width`를 활용해 한글 2바이트 전각 문자의 너비를 정확히 계산하여 표가 삐뚤어지지 않고 완벽하게 정렬됩니다.

```bash
$ python -m budget_app list --table
+-----------+------------+---------+-----------+-------------+--------+--------+
|    ID     |    날짜    |  타입   | 카테고리  |    금액     |  메모  |  태그  |
+-----------+------------+---------+-----------+-------------+--------+--------+
| TX-000002 | 2024-01-15 | expense | 식비      |    15,000원 | 점심   | 외식   |
| TX-000001 | 2024-01-10 | income  | 급여      | 3,000,000원 | 1월급여 | 월급   |
+-----------+------------+---------+-----------+-------------+--------+--------+
```

---

## 📊 CSV Import / Export 규격 명세

`import` 및 `export`는 아래 고정된 최소 스키마(UTF-8, 헤더 포함)를 완벽히 준수합니다.

| Column | Required | Type | 설명 및 예시 |
| :--- | :---: | :--- | :--- |
| **`date`** | **Y** | 문자열 | 거래 일자 (`YYYY-MM-DD`, 예: `2024-01-15`) |
| **`type`** | **Y** | 문자열 | 거래 유형 (`income` 또는 `expense`) |
| **`category`** | **Y** | 문자열 | 등록된 카테고리명 (import 시 미등록 카테고리는 자동 등록) |
| **`amount`** | **Y** | 정수 | 0 초과의 양의 정수 (예: `15000`) |
| **`memo`** | N | 문자열 | 거래 메모 설명 |
| **`tags`** | N | 문자열 | 쉼표(`,`)로 구분된 태그 목록 (예: `점심,외식`) |

---

## 🧪 테스트 실행 방법

본 프로젝트는 Python 표준 라이브러리 `unittest`를 기반으로 모델 검증, 저장소 원자성/스트리밍, 서비스 로직, 데코레이터, 포맷터, CLI 통합 테스트까지 **총 37개의 단위/통합 테스트**를 갖추고 있습니다.

```bash
# 전체 테스트 실행
python3 -m unittest discover tests -v
```

실행 결과:
```
Ran 37 tests in 0.048s
OK
```
모든 테스트가 오류 없이 즉시 통과함을 확인할 수 있습니다.
