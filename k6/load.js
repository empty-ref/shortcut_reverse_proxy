import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate } from 'k6/metrics';

export const options = {
  scenarios: {
    steady_load: {
      executor: 'constant-vus',
      vus: Number(__ENV.VUS || 2000),
      duration: __ENV.DURATION || '120s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<800'],
  },
  noConnectionReuse: false,
  noVUConnectionReuse: false,
};

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8080';
const REQUEST_PATH = '/hello?from=k6';

const networkErrors = new Counter('network_errors');
const connectAddrErrors = new Counter('connect_addr_errors');
const status200 = new Counter('status_200');
const status502 = new Counter('status_502');
const status503 = new Counter('status_503');
const statusOther = new Counter('status_other');

export default function () {
  const res = http.get(`${BASE_URL}${REQUEST_PATH}`, {
    headers: {
      Connection: 'keep-alive',
    },
  });

  const hasNetworkError = !!res.error;

  if (hasNetworkError) {
    networkErrors.add(1);
    if (String(res.error).includes("can't assign requested address")) {
      connectAddrErrors.add(1);
    }
  } else if (res.status === 200) {
    status200.add(1);
  } else if (res.status === 502) {
    status502.add(1);
  } else if (res.status === 503) {
    status503.add(1);
  } else {
    statusOther.add(1);
  }

  check(res, {
    'status is 200': (r) => r.status === 200
  });

  sleep(0.2);
}
