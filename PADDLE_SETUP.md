# WEE Premium Paddle Sandbox 연동

## API

- `POST /api/premium/checkout/` (JWT 필요): 서버의 `PADDLE_PRICE_ID`로 Paddle 거래를 만들고 `transactionId`를 반환합니다.
- `POST /api/premium/webhooks/paddle/` (Paddle 전용): 원문 body와 `Paddle-Signature`를 검증한 뒤 이벤트를 처리합니다.
- `GET /api/premium/status/` (JWT 필요): 현재 프리미엄 활성 여부와 시작/만료 시각을 반환합니다.
- `GET|PUT|PATCH /api/premium/profile/`, `GET|PUT|PATCH /api/premium/notification-settings/`: 활성 프리미엄 이용권이 있어야 접근할 수 있습니다.

성공 화면이나 Paddle.js의 `checkout.completed` 이벤트는 UX에만 사용합니다. 권한은 서명이 검증된 `transaction.completed` Webhook만 지급합니다.

## 환경변수

EC2의 `/home/ubuntu/srv/ubuntu/.env.prod`와 GitHub Actions의 `ENV_VARS` secret에 다음 값을 넣습니다. 실제 값은 커밋하지 않습니다.

```dotenv
PADDLE_API_KEY=pdl_sdbx_apikey_...
PADDLE_ENVIRONMENT=sandbox
PADDLE_WEBHOOK_SECRET=pdl_ntfset_...
PADDLE_PRICE_ID=pri_...
```

Vite 프론트엔드에는 별도로 다음 값을 둡니다.

```dotenv
VITE_PADDLE_CLIENT_TOKEN=test_...
VITE_PADDLE_ENVIRONMENT=sandbox
```

## 프론트엔드 Checkout 호출

구매 버튼은 먼저 JWT와 함께 백엔드의 `POST /api/premium/checkout/`을 호출해야 합니다. 응답의 `transactionId`만 Paddle Checkout에 넘깁니다. 프론트에서 Price ID나 사용자 ID를 조립하지 않습니다.

```ts
import { initializePaddle } from "@paddle/paddle-js";

const paddle = await initializePaddle({
  token: import.meta.env.VITE_PADDLE_CLIENT_TOKEN,
  environment: import.meta.env.VITE_PADDLE_ENVIRONMENT,
});

const response = await fetch(`${API_BASE_URL}/api/premium/checkout/`, {
  method: "POST",
  headers: { Authorization: `Bearer ${accessToken}` },
});
const { transactionId } = await response.json();
paddle?.Checkout.open({ transactionId });
```

Checkout 완료 화면에서는 `GET /api/premium/status/`를 짧은 간격으로 다시 조회할 수 있지만, 그 화면 자체로 권한을 지급하지 않습니다.

## Paddle Sandbox 대시보드

1. WEE Premium 가격이 **one-time**, `KRW 2,500`, 세금 포함 가격인지 확인하고 그 `pri_...` 값을 `PADDLE_PRICE_ID`에 넣습니다. 할인 코드 사용은 꺼 둡니다. 이 서버는 최종 합계 2,500원만 승인합니다.
2. **Checkout > Checkout configuration**에서 Sandbox 기본 결제 링크를 프론트엔드의 Paddle.js 페이지로 지정합니다. Sandbox에서는 localhost도 사용할 수 있습니다.
3. **Developer tools > Notifications**에서 새 Webhook destination을 만들고 아래 HTTPS URL을 정확히 등록합니다.

   `https://<백엔드-도메인>/api/premium/webhooks/paddle/`

   예를 들어 백엔드 도메인이 `api.weether.kr`이면 정확한 URL은 `https://api.weether.kr/api/premium/webhooks/paddle/`입니다. 뒤의 `/`까지 포함합니다.
4. 이벤트는 `transaction.completed`, `transaction.payment_failed`, `transaction.past_due`, `transaction.canceled`, `transaction.updated`, `adjustment.created`, `adjustment.updated`를 구독합니다.
5. destination 생성 후 표시되는 endpoint secret을 `PADDLE_WEBHOOK_SECRET`에 넣습니다. API key나 client-side token이 아닙니다.

## EC2 배포

현재 저장소는 `dev` push 시 GitHub Actions가 이미지를 만들고 `/home/ubuntu/srv/ubuntu`에 동기화한 뒤 Docker Compose를 재시작합니다. 따라서 이 브랜치를 PR로 `dev`에 병합하기 전에 다음을 준비합니다.

1. GitHub repository secret `ENV_VARS`에 위 Paddle 백엔드 환경변수 4개를 추가합니다.
2. EC2 보안 그룹은 외부에 443만 공개하고, Nginx/ALB에서 `https://<백엔드-도메인>`을 컨테이너의 `127.0.0.1:8000`으로 프록시합니다. Paddle Webhook은 공개 HTTPS URL이어야 합니다.
3. `dev` 병합/푸시 후 Actions의 **Django Docker Image Build & Deploy** 완료를 확인합니다. 컨테이너 시작 명령이 `python manage.py migrate`를 실행하므로 신규 migration도 자동 적용됩니다.
4. EC2에서 확인합니다.

```bash
cd /home/ubuntu/srv/ubuntu
sudo docker compose --env-file .env.prod -f docker-compose.prod.yml ps
sudo docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=200 web
curl -i https://<백엔드-도메인>/
```

도메인/TLS가 아직 없다면 EC2의 `http://<public-ip>:8000`을 Paddle에 등록하지 말고, 먼저 Nginx + 인증서 또는 HTTPS를 제공하는 ALB를 구성합니다.

## 권한 및 환불 정책

- 첫 결제: `transaction.completed`의 `occurred_at`부터 21일을 부여합니다.
- 재구매: 아직 남은 기간이 있으면 현재 만료 시각 뒤에 21일을 이어 붙입니다.
- 실패/취소: 구매 상태만 `FAILED`/`CANCELED`로 바꾸고 권한은 지급하지 않습니다.
- 승인된 부분 환불: `PARTIALLY_REFUNDED`로 기록하되 권한은 유지합니다.
- 승인된 전액 환불/차지백: 환불된 구매에서 아직 사용하지 않은 시간만 총 만료 시각에서 차감합니다. 이미 사용한 기간과 다른 정상 구매의 21일은 유지합니다.
- 동일 `event_id`는 `PaddleWebhookEvent`의 PK로 한 번만 처리하고, 같은 거래의 권한 지급 여부도 별도로 확인합니다.

## 로컬/샌드박스 테스트

```bash
python manage.py migrate
python manage.py test premium situations.tests.DailyNotificationPreferenceSchedulerTests
```

로컬 서버를 Paddle에서 호출하려면 HTTPS 터널을 사용해 터널 URL 뒤에 `/api/premium/webhooks/paddle/`을 붙입니다. Sandbox Checkout 테스트 카드는 성공 `4242 4242 4242 4242`, 실패 `4000 0000 0000 0002`이며 만료일은 미래 날짜, CVC는 `100`을 사용할 수 있습니다.

- 성공: Checkout 후 `transaction.completed` delivery가 200인지, status API가 활성인지 확인합니다.
- 실패: declined 카드 후 구매 상태와 Webhook delivery를 확인합니다.
- 취소: Paddle Webhook simulator에서 `transaction.canceled`를 보내 권한이 생기지 않는지 확인합니다.
- 환불: Sandbox 거래를 전액 refund하고 `adjustment.created`/`adjustment.updated` 후 권한이 회수되는지 확인합니다.
- 중복: Paddle dashboard에서 같은 notification을 replay해 만료일이 늘어나지 않는지 확인합니다.
