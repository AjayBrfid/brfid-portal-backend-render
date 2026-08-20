"""Domain exception hierarchy. Every AppException subclass carries an HTTP status and a
machine-readable `code` so the global handlers (registered in main.py) can turn any of these
into the unified `{"success": false, "error": {code, message, details}}` envelope without each
router needing its own try/except.
"""


class AppException(Exception):
    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, details: list | None = None):
        self.message = message
        self.details = details
        super().__init__(message)


class NotFoundException(AppException):
    status_code = 404
    code = "NOT_FOUND"


class ValidationException(AppException):
    status_code = 422
    code = "VALIDATION_ERROR"


class ConflictException(AppException):
    status_code = 409
    code = "CONFLICT"


class ForbiddenException(AppException):
    status_code = 403
    code = "FORBIDDEN"


class BadRequestException(AppException):
    status_code = 400
    code = "BAD_REQUEST"


class UnauthorizedException(AppException):
    status_code = 401
    code = "UNAUTHORIZED"


class InvalidCredentialsException(AppException):
    status_code = 401
    code = "INVALID_CREDENTIALS"


class PortalAccessNotApprovedException(ForbiddenException):
    code = "PORTAL_ACCESS_NOT_APPROVED"

    def __init__(self, entity_status: str, entity_label: str = "Vendor"):
        super().__init__(f"Portal access is not available. {entity_label} account status is '{entity_status}'.")


class InvalidTokenException(AppException):
    status_code = 401
    code = "INVALID_TOKEN"


class UserNotFoundException(NotFoundException):
    code = "USER_NOT_FOUND"

    def __init__(self):
        super().__init__("User not found")


class EmailAlreadyExistsException(ConflictException):
    code = "EMAIL_EXISTS"

    def __init__(self):
        super().__init__("A user with this email already exists in this portal")


class RoleNotCreatableException(ForbiddenException):
    code = "ROLE_NOT_CREATABLE"

    def __init__(self, role: str):
        super().__init__(f"Role '{role}' cannot be assigned via user creation for this portal")


class CannotModifySelfStatusException(ForbiddenException):
    code = "CANNOT_MODIFY_SELF_STATUS"

    def __init__(self):
        super().__init__("You cannot deactivate your own account")


class UnsupportedFileTypeException(BadRequestException):
    code = "UNSUPPORTED_FILE_TYPE"

    def __init__(self, extension: str):
        super().__init__(f"File type '{extension}' is not supported")


class FileTooLargeException(BadRequestException):
    code = "FILE_TOO_LARGE"

    def __init__(self, max_bytes: int):
        super().__init__(f"File exceeds the maximum allowed size of {max_bytes} bytes")


class InvalidStateTransitionException(ConflictException):
    code = "INVALID_STATE_TRANSITION"
