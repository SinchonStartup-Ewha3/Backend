# WEE Premium · 운세 PayApp 연동

WEE Premium은 PayApp 일회성 결제로 2,500원을 결제한 사용자에게 21일 권한을 지급합니다. 결제 완료 페이지는 안내 용도이며, 권한은 PayApp의 서버 통보를 검증한 뒤에만 지급합니다.

운세는 `FortuneProduct`에 저장된 1·7·14·21일 상품 가격으로 결제를 요청하고, 검증된 PayApp 서버 통보가 도착한 뒤에만 해당 기간의 상세 운세를 엽니다.

## API

- `POST /api/premium/payapp/checkout/` (JWT 필요)
  - 요청: `{"recvphone": "01012345678"}`
  - 응답의 `paymentUrl`을 브라우저에서 엽니다.
- `POST /api/premium/webhooks/payapp/` (PayApp 서버 전용)
  - PayApp의 FORM POST 통보를 검증합니다.
  - 정상 처리 시 HTTP 200과 본문 `SUCCESS`를 반환합니다.
- `GET /api/premium/status/` (JWT 필요)
  - 현재 Premium 활성 여부와 만료 시각을 반환합니다.
- `POST /api/fortune/payapp/checkout/` (JWT 필요)
  - 요청: `{"product_id": 2, "recvphone": "01012345678"}`
  - 서버가 상품명과 가격을 조회해 주문을 만들고 `purchaseId`, `paymentUrl`을 반환합니다.
- `POST /api/fortune/webhooks/payapp/` (PayApp 서버 전용)
  - 운세 주문 토큰, 상품명, 가격, 결제요청번호를 검증하고 이용권을 활성화합니다.
- `GET /api/fortune/purchases/<purchaseId>/` (JWT 필요)
  - 결제 결과 화면에서 본인 주문의 `payment_status`를 조회합니다.

## 환경변수

실제 값은 Git이나 프론트엔드 코드에 넣지 말고 EC2의 `.env.prod`에만 저장합니다.

```env
PAYAPP_USER_ID=<판매자 아이디>
PAYAPP_LINK_KEY=<연동 KEY>
PAYAPP_LINK_VALUE=<연동 VALUE>
PAYAPP_REQUEST_KEY=<결제 KEY>
PAYAPP_FEEDBACK_URL=https://<백엔드 도메인>/api/premium/webhooks/payapp/
# 프론트 결제 결과 화면을 만들기 전에는 비워둡니다.
PAYAPP_RETURN_URL=
PAYAPP_FORTUNE_FEEDBACK_URL=https://<백엔드 도메인>/api/fortune/webhooks/payapp/
# 프론트 운세 결제 결과 화면을 만들기 전에는 비워둡니다.
PAYAPP_FORTUNE_RETURN_URL=
PAYAPP_OPEN_PAY_TYPE=
PAYAPP_TIMEOUT_SECONDS=10
```

`PAYAPP_OPEN_PAY_TYPE`을 비워두면 판매자센터의 결제수단 설정을 사용합니다. 특정 수단만 허용할 때는 PayApp 문서의 코드 값을 쉼표로 연결합니다. 과세·면세 금액은 운영 정책 확인 전에는 API에 임의로 전송하지 않습니다.

## 배포

1. 현재 변경사항을 배포 이미지에 포함합니다.
2. EC2 `.env.prod`에 환경변수를 추가합니다.
3. `python manage.py migrate`로 `premium.0010_payapp_payments`와 `fortune.0008_fortune_payapp`을 적용합니다.
4. 판매자센터의 공통 통보 URL은 비워둡니다. WEE는 각 결제 요청에 `feedbackurl`을 포함하므로 공통 통보 URL이 필요하지 않습니다.
5. 로그인 사용자의 JWT로 checkout API를 호출하고 반환된 `paymentUrl`을 엽니다.
6. 결제 후 Premium status 또는 운세 purchase API와 Django Admin의 PayApp 결제 내역을 확인합니다.

## 검증 및 중복 방지

서버는 판매자 아이디, 연동 KEY, 연동 VALUE, `sha256(userid + responsedate + requestkey)`, 주문 토큰, 상품 식별자, 결제요청번호, 상품명, 2,500원을 검증합니다. `pay_state=4`일 때만 권한을 지급합니다. 동일한 통보가 반복되어도 통보 키와 결제별 지급 시각을 사용해 21일을 중복 지급하지 않습니다.

운세 결제도 같은 판매자 인증값을 검증하되, 금액과 이용 기간은 선택한 `FortuneProduct`의 서버 저장값만 사용합니다. 프론트엔드가 보낸 가격은 받지 않습니다. 동시에 완료된 복수 주문은 이용 기간 뒤에 이어 붙여 결제한 기간이 사라지지 않게 합니다.

## 환불

사용자는 앱에서 환불 사유를 입력해 환불 요청을 접수합니다. 요청 즉시 해당 결제의 남은 Premium 이용 기간은 심사 중 일시 중단됩니다.

운영진은 Django Admin의 Premium 환불 요청에서 요청 금액을 확인하고 다음 순서로 처리합니다.

1. PayApp 관리자에서 실제 환불을 처리합니다.
2. 해당 요청을 선택하고 `PayApp에서 환불한 선택 요청을 승인·완료 처리` 액션을 실행합니다.
3. 환불이 불가능하면 거절 사유를 입력한 뒤 환불 거절 액션을 실행합니다. 거절 시 요청 때 중단한 잔여 이용 기간이 복구됩니다.

PayApp 환불 자체는 자동 호출하지 않습니다. 관리자 액션은 PayApp에서 실제 환불을 마친 뒤에만 실행해야 합니다. PayApp 승인 취소 통보는 거래 상태를 기록하지만 사용자 환불 요청의 운영진 승인·거절 절차를 대신하지 않습니다.
