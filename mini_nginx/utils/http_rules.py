from http import HTTPMethod, HTTPStatus


def response_must_not_have_body(method: str, status_code: int) -> bool:
    if method.upper() == HTTPMethod.HEAD.value:
        return True
    if HTTPStatus.CONTINUE.value <= status_code < HTTPStatus.OK.value:
        return True
    if status_code in (HTTPStatus.NO_CONTENT.value, HTTPStatus.NOT_MODIFIED.value):
        return True
    return False
