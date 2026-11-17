# 변경안 (미적용) — `stage4k.identity`의 placement 기대값을 명시 인자로

## 문제

`stage4k.identity(folder, wl, cfg, caps_ref)`는 `placement == 0`을 고정한다. 이를 상속하는 `stage4aoe.identity_a1`과 `stage6bb.identity_of`를 쓰는 새 실험에서 SRAM 배치(placement 1)가 항상 거부된다(E2D boot 442).

## 제안

1. `identity(..., expected_placement: int = 0)`로 바꾼다. 기본값 0이므로 기존 호출(4K, 4AO, 4AO-E, 4WD, 6B-B, E1, E1-R, E2B)의 결과는 같다.
2. `identity_a1`은 DRWL header에서 구한 `expected["placement"]`를 넘긴다. manifest와 header가 다르면(`agree` 거짓) 이미 실패한다.
3. `stage6bb.identity_of`는 manifest의 `placement`가 있으면 넘긴다.
4. 회귀 검사:
   - 저장소의 모든 identity 경로 실험을 바뀐 코드로 다시 판정한다. 각 실험의 summary가 바이트 단위로 같아야 한다(모두 placement 0이므로 같아야 함).
   - E2D 정정 판정과도 같은 결과여야 한다.
5. 테스트:
   - DRAM/SRAM 기대·관측 4조합
   - REGIONCFG 조작
   - manifest와 header 불일치
   - 기본값 하위 호환(기존 테스트 전부)
6. mutation:
   - 기대값 무시
   - 관측 무시
   - 기본값 변경

적용하려면 별도 승인이 필요하다. 그때까지 새 실험은 E2D처럼 단계별 판정 계층에서 placement 항을 정정한다.
