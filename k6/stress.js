import http from 'k6/http';
import { check, sleep } from 'k6';

const VUS = __ENV.VUS ? Number(__ENV.VUS) : 20;

export const options = {
  stages: [
    { duration: '10s', target: VUS },
    { duration: '20s', target: VUS },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.02'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8080';

export default function () {
  const res = http.get(`${BASE_URL}/stress`, { headers: { Connection: 'keep-alive' } });
  check(res, { 'status is 200': (r) => r.status === 200 });
  sleep(0.1);
}
