"""Fixed relevance criteria, defined before comparing BGE on/off.

These measure retrieval of evidence already in the project corpus, not the
medical/fire safety validity of that corpus or generated answers.
"""
import hashlib

APARTMENT = "(아파트 입주자) 화재 피난행동요령.pdf"
EDGE = "edge_saver_manual.txt"
FACTORY = "factory_fire_manual.txt"


def case(query, category, sources, *groups):
    return dict(query=query, category=category, sources=sources, evidence_groups=groups)


CASES = [
    case("A구역 화재시 대피방법은?", "zone", ["zone_A_layout.txt"], ["북쪽 로비"], ["주차장"]),
    case("A구역 정문이 막혔는데 어디로 탈출해?", "zone", ["zone_A_layout.txt"], ["정문이 막힌"], ["비상대피창"]),
    case("b 구역 비상 탈출 경로 알려줘", "zone", ["zone_B_layout.txt"], ["동쪽 비상구"]),
    case("B구역 소화기 어디 있어?", "zone", ["zone_B_layout.txt"], ["A3 기둥"], ["소화기"]),
    case("C구역에서 불이 났는데 어디로 대피해?", "zone", ["zone_C_layout.txt"], ["비상계단"], ["잔디밭"]),
    case("zone_C 엘리베이터로 내려가도 되나?", "zone", ["zone_C_layout.txt"], ["엘리베이터"], ["금지"]),
    case("사람이 숨을 안쉬는데 어떡해?", "medical", [EDGE], ["심폐소생", "CPR"], ["가슴 압박", "가슴압박"]),
    case("호흡이 없어요", "medical", [EDGE], ["심폐소생", "CPR"], ["가슴 압박", "가슴압박"]),
    case("의식이 없어요", "medical", [EDGE], ["의식"], ["호흡"], ["압박"]),
    case("숨을 안 쉰다", "medical", [EDGE], ["심폐소생", "CPR"], ["가슴 압박", "가슴압박"]),
    case("심폐소생술 방법 알려줘", "medical", [EDGE], ["심폐소생", "CPR"], ["압박"]),
    case("심폐소생술 가슴 압박 속도는?", "medical", [EDGE], ["100~120"]),
    case("피가 멈추지 않고 철철 흘러 지혈 어떻게 하지?", "medical", [EDGE], ["지혈"], ["압박"]),
    case("높은 곳에서 떨어져서 뼈가 부러진 것 같아요", "medical", [EDGE], ["골절"], ["부목", "경추"]),
    case("공장 화재시 대처방법은?", "factory", [FACTORY], ["화재"], ["차단기", "비상", "소화기"]),
    case("공장 배전반에 불이 났는데 물 뿌려도 되나?", "factory", [FACTORY], ["전기 화재"], ["물"], ["차단기"]),
    case("공장 화학용제에 불이 붙었을 때 소화 방법은?", "factory", [FACTORY], ["화학용제"], ["거품", "포말", "모래"]),
    case("공장 창고의 종이와 박스가 타는데 어떤 소화 설비를 써?", "factory", [FACTORY], ["박스", "종이"], ["옥내 소화전", "옥내소화전"]),
    case("공장 컨베이어에서 불꽃이 튀면 먼저 뭘 해야 해?", "factory", [FACTORY], ["비상 정지", "E-STOP"]),
    case("공장 불이 다른 작업 구역으로 번지는데 방화문 어떻게 해?", "factory", [FACTORY], ["방화문"], ["닫고"]),
    case("공장 화재 집결지에 도착한 다음 해야 할 일은?", "factory", [FACTORY], ["집결지"], ["인원 파악", "출석 체크"]),
    case("기계 벨트에 팔이 끼었어 전원 어떻게 해?", "factory", [EDGE], ["끼임"], ["전원"], ["차단"]),
    case("아파트에서 화재가 발생하면 어떻게 대피하나요?", "apartment", [APARTMENT], ["계단"], ["대피한다", "대피합니다"]),
    case("아파트 이웃집에 불났는데 우리 집에 연기가 안 들어오면?", "apartment", [APARTMENT], ["들어오지 않는", "들어오지 않음"], ["대기"], ["주시", "모니터링"]),
    case("아파트 복도에 연기가 가득해서 대피할 수 없으면?", "apartment", [APARTMENT], ["대피가 어려운", "대피가 곤란"], ["틈새"], ["구조"]),
    case("아파트 화재 때 엘리베이터 타도 돼?", "apartment", [APARTMENT], ["엘리베이터", "엘리베"], ["타지", "금지", "이용하지"]),
    case("산에서 길을 잃고 조난당했을 때 수칙", "mountain", [EDGE], ["길을 잃었"], ["체온"]),
    case("산사태나 낙석이 발생했을 때 대처 방법", "mountain", [EDGE], ["낙석", "산사태"], ["구조물"]),
]


def chunk_id(doc):
    return hashlib.sha256((doc.get("source", "") + "\n" + doc.get("page_content", "")).encode("utf-8")).hexdigest()


def gold_chunks(documents, item):
    return [chunk_id(doc) for doc in documents if doc.get("source") in item["sources"]
            and all(any(term.lower() in doc.get("page_content", "").lower() for term in group)
                    for group in item["evidence_groups"])]
