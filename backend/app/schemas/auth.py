"""
Pydantic request/response schemas for authentication.
"""
import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
PHONE_REGEX = re.compile(r"^\+?[1-9]\d{6,14}$")

PASSWORD_MIN_LENGTH = 8


def _validate_email(v: str) -> str:
    v = v.strip().lower()
    if not EMAIL_REGEX.match(v):
        raise ValueError("Invalid email format.")
    return v


def _validate_phone(v: str) -> str:
    v = v.strip().replace(" ", "").replace("-", "")
    if not PHONE_REGEX.match(v):
        raise ValueError("Invalid phone number. Use international format e.g. +919876543210.")
    return v


def _validate_password(v: str) -> str:
    if len(v) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
    if not re.search(r"[A-Z]", v):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", v):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", v):
        raise ValueError("Password must contain at least one digit.")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", v):
        raise ValueError("Password must contain at least one special character.")
    return v


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., max_length=255)
    phone: str = Field(..., max_length=20)
    password: str = Field(..., min_length=8)
    password_confirmation: str = Field(...)
    verification_method: str = Field(default="email")  # "email" | "phone"

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        return _validate_email(v)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        return _validate_phone(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        return _validate_password(v)

    @field_validator("password_confirmation")
    @classmethod
    def validate_password_confirmation(cls, v, info):
        password = info.data.get("password")
        if password and v != password:
            raise ValueError("Passwords do not match.")
        return v

    @field_validator("verification_method")
    @classmethod
    def validate_method(cls, v):
        if v not in ("email", "phone"):
            raise ValueError("verification_method must be 'email' or 'phone'.")
        return v


class SignupResponse(BaseModel):
    user_id: str
    message: str
    verification_method: str


# ---------------------------------------------------------------------------
# OTP Verification
# ---------------------------------------------------------------------------

class VerifyOTPRequest(BaseModel):
    user_id: str
    otp: str = Field(..., min_length=4, max_length=8)


class VerifyOTPResponse(BaseModel):
    verified: bool
    access_token: Optional[str] = None
    message: str


class ResendOTPRequest(BaseModel):
    user_id: str
    method: str = Field(default="email")  # "email" | "phone"

    @field_validator("method")
    @classmethod
    def validate_method(cls, v):
        if v not in ("email", "phone"):
            raise ValueError("method must be 'email' or 'phone'.")
        return v


class ResendOTPResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    identifier: str = Field(..., min_length=1)  # email or phone
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserPublic"


# ---------------------------------------------------------------------------
# Forgot / Reset Password
# ---------------------------------------------------------------------------

class ForgotPasswordRequest(BaseModel):
    identifier: str = Field(..., min_length=1)  # email or phone
    method: str = Field(default="email")  # "email" | "phone"

    @field_validator("method")
    @classmethod
    def validate_method(cls, v):
        if v not in ("email", "phone"):
            raise ValueError("method must be 'email' or 'phone'.")
        return v


class ForgotPasswordResponse(BaseModel):
    message: str
    user_id: str


class VerifyResetOTPRequest(BaseModel):
    user_id: str
    otp: str = Field(..., min_length=4, max_length=8)


class VerifyResetOTPResponse(BaseModel):
    reset_token: str
    message: str


class ResetPasswordRequest(BaseModel):
    user_id: str
    reset_token: str
    new_password: str = Field(..., min_length=8)
    new_password_confirmation: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        return _validate_password(v)

    @field_validator("new_password_confirmation")
    @classmethod
    def validate_password_confirmation(cls, v, info):
        password = info.data.get("new_password")
        if password and v != password:
            raise ValueError("Passwords do not match.")
        return v


class ResetPasswordResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserPublic(BaseModel):
    user_id: str
    name: str
    email: str
    phone: str
    is_verified: bool

    class Config:
        from_attributes = True


class UserProfileResponse(BaseModel):
    user: UserPublic


# Needed for forward reference resolution
LoginResponse.model_rebuild()
