import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    steady_load: {
      executor: 'constant-vus',
      vus: Number(__ENV.VUS || 100),
      duration: __ENV.DURATION || '20s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<800'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8080';

export default function () {
  const res = http.get(`${BASE_URL}/hello?from=k6`, {
    headers: {
      Connection: 'application-json',
    },
  });

  check(res, {
    'status is 200': (r) => r.status === 200
  });

  sleep(0.1);
}
