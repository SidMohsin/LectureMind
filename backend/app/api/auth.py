"""
REST API routes for authentication: signup, OTP verification, login,
forgot password, reset password, and user profile.
"""
import datetime as dt
import logging

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User, OTP, PasswordResetToken
from app.schemas.auth import (
    SignupRequest, SignupResponse,
    VerifyOTPRequest, VerifyOTPResponse,
    ResendOTPRequest, ResendOTPResponse,
    LoginRequest, LoginResponse,
    ForgotPasswordRequest, ForgotPasswordResponse,
    VerifyResetOTPRequest, VerifyResetOTPResponse,
    ResetPasswordRequest, ResetPasswordResponse,
    UserPublic, UserProfileResponse,
)
from app.services.auth_service import (
    hash_password, verify_password,
    create_access_token,
    generate_otp, hash_otp, verify_otp,
    generate_reset_token, hash_token, verify_token,
)
from app.services.notification_service import send_otp as send_otp_notification, NotificationError
from app.api.deps import get_current_user

logger = logging.getLogger("lecturemind.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_user_by_identifier(db: Session, identifier: str):
    """Find a user by email or phone."""
    identifier = identifier.strip().lower()
    user = db.query(User).filter(User.email == identifier).first()
    if not user:
        # Try phone (strip spaces/dashes)
        cleaned = identifier.replace(" ", "").replace("-", "")
        user = db.query(User).filter(User.phone == cleaned).first()
    return user


def _create_and_send_otp(db: Session, user: User, purpose: str, method: str) -> OTP:
    """Generate OTP, hash it, store it, and send it to the user."""
    otp_plain = generate_otp()
    otp_record = OTP(
        user_id=user.user_id,
        otp_hash=hash_otp(otp_plain),
        purpose=purpose,
        method=method,
        attempts=0,
        is_used=False,
        created_at=dt.datetime.utcnow(),
        expires_at=dt.datetime.utcnow() + dt.timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
    )
    db.add(otp_record)
    db.commit()

    # Determine destination
    destination = user.email if method == "email" else user.phone

    try:
        send_otp_notification(otp_plain, method, destination)
    except NotificationError as e:
        logger.error(f"Failed to send OTP to {destination}: {e}")
        # Don't expose the failure detail, but log it
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification code. Please try again.",
        )

    return otp_record


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------

@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(req: SignupRequest, db: Session = Depends(get_db)):
    # Check duplicate email
    existing_email = db.query(User).filter(User.email == req.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # Check duplicate phone
    existing_phone = db.query(User).filter(User.phone == req.phone).first()
    if existing_phone:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this phone number already exists.",
        )

    # Create user in unverified state
    user = User(
        name=req.name.strip(),
        email=req.email,
        phone=req.phone,
        password_hash=hash_password(req.password),
        is_verified=False,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"New user signup: {user.email} (id={user.user_id})")

    # Send OTP
    _create_and_send_otp(db, user, purpose="signup", method=req.verification_method)

    return SignupResponse(
        user_id=user.user_id,
        message=f"Account created. A verification code has been sent to your {req.verification_method}.",
        verification_method=req.verification_method,
    )


# ---------------------------------------------------------------------------
# OTP Verification (Signup)
# ---------------------------------------------------------------------------

@router.post("/verify", response_model=VerifyOTPResponse)
def verify_account(req: VerifyOTPRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account is already verified.")

    # Find the latest unused signup OTP for this user
    otp_record = (
        db.query(OTP)
        .filter(
            OTP.user_id == req.user_id,
            OTP.purpose == "signup",
            OTP.is_used == False,
        )
        .order_by(OTP.created_at.desc())
        .first()
    )

    if not otp_record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending verification code found. Please request a new one.")

    # Check expiry
    if dt.datetime.utcnow() > otp_record.expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code has expired. Please request a new one.")

    # Check max attempts
    if otp_record.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many failed attempts. Please request a new verification code.")

    # Verify
    otp_record.attempts += 1
    db.commit()

    if not verify_otp(req.otp, otp_record.otp_hash):
        remaining = settings.OTP_MAX_ATTEMPTS - otp_record.attempts
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid verification code. {remaining} attempt(s) remaining.",
        )

    # Mark OTP as used and activate account
    otp_record.is_used = True
    user.is_verified = True
    db.commit()

    logger.info(f"Account verified: {user.email} (id={user.user_id})")

    # Auto-login: issue access token
    token = create_access_token(user.user_id)

    return VerifyOTPResponse(
        verified=True,
        access_token=token,
        message="Account verified successfully.",
    )


# ---------------------------------------------------------------------------
# Resend OTP
# ---------------------------------------------------------------------------

@router.post("/resend-otp", response_model=ResendOTPResponse)
def resend_otp(req: ResendOTPRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Check cooldown: find the most recent OTP for this user
    latest_otp = (
        db.query(OTP)
        .filter(OTP.user_id == req.user_id)
        .order_by(OTP.created_at.desc())
        .first()
    )
    if latest_otp:
        seconds_since = (dt.datetime.utcnow() - latest_otp.created_at).total_seconds()
        if seconds_since < settings.OTP_RESEND_COOLDOWN_SECONDS:
            wait = int(settings.OTP_RESEND_COOLDOWN_SECONDS - seconds_since)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {wait} seconds before requesting a new code.",
            )

    # Determine purpose
    purpose = "signup" if not user.is_verified else "password_reset"

    _create_and_send_otp(db, user, purpose=purpose, method=req.method)

    return ResendOTPResponse(message=f"A new verification code has been sent to your {req.method}.")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = _find_user_by_identifier(db, req.identifier)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email/phone or password.",
        )

    if not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email/phone or password.",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not verified. Please verify your account first.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    token = create_access_token(user.user_id)
    logger.info(f"User login: {user.email} (id={user.user_id})")

    return LoginResponse(
        access_token=token,
        user=UserPublic(
            user_id=user.user_id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            is_verified=user.is_verified,
        ),
    )


# ---------------------------------------------------------------------------
# Forgot Password
# ---------------------------------------------------------------------------

@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = _find_user_by_identifier(db, req.identifier)

    # Don't reveal whether the user exists — always return success-like message
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with this email or phone number.",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not verified. Please verify your account first.",
        )

    # Check cooldown
    latest_otp = (
        db.query(OTP)
        .filter(OTP.user_id == user.user_id, OTP.purpose == "password_reset")
        .order_by(OTP.created_at.desc())
        .first()
    )
    if latest_otp:
        seconds_since = (dt.datetime.utcnow() - latest_otp.created_at).total_seconds()
        if seconds_since < settings.OTP_RESEND_COOLDOWN_SECONDS:
            wait = int(settings.OTP_RESEND_COOLDOWN_SECONDS - seconds_since)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {wait} seconds before requesting a new code.",
            )

    _create_and_send_otp(db, user, purpose="password_reset", method=req.method)

    return ForgotPasswordResponse(
        message=f"A verification code has been sent to your {req.method}.",
        user_id=user.user_id,
    )


# ---------------------------------------------------------------------------
# Verify Reset OTP
# ---------------------------------------------------------------------------

@router.post("/verify-reset-otp", response_model=VerifyResetOTPResponse)
def verify_reset_otp(req: VerifyResetOTPRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    otp_record = (
        db.query(OTP)
        .filter(
            OTP.user_id == req.user_id,
            OTP.purpose == "password_reset",
            OTP.is_used == False,
        )
        .order_by(OTP.created_at.desc())
        .first()
    )

    if not otp_record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending verification code found.")

    if dt.datetime.utcnow() > otp_record.expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code has expired.")

    if otp_record.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many failed attempts. Please request a new code.")

    otp_record.attempts += 1
    db.commit()

    if not verify_otp(req.otp, otp_record.otp_hash):
        remaining = settings.OTP_MAX_ATTEMPTS - otp_record.attempts
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid code. {remaining} attempt(s) remaining.")

    otp_record.is_used = True
    db.commit()

    # Generate a short-lived reset token
    reset_token_plain = generate_reset_token()
    reset_record = PasswordResetToken(
        user_id=user.user_id,
        token_hash=hash_token(reset_token_plain),
        is_used=False,
        expires_at=dt.datetime.utcnow() + dt.timedelta(minutes=15),
    )
    db.add(reset_record)
    db.commit()

    return VerifyResetOTPResponse(
        reset_token=reset_token_plain,
        message="Verification successful. You can now reset your password.",
    )


# ---------------------------------------------------------------------------
# Reset Password
# ---------------------------------------------------------------------------

@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Find a valid reset token
    reset_record = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.user_id == req.user_id,
            PasswordResetToken.is_used == False,
        )
        .order_by(PasswordResetToken.created_at.desc())
        .first()
    )

    if not reset_record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid reset token found. Please restart the password reset process.")

    if dt.datetime.utcnow() > reset_record.expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token has expired. Please restart the process.")

    if not verify_token(req.reset_token, reset_record.token_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token.")

    # Update password
    user.password_hash = hash_password(req.new_password)
    reset_record.is_used = True
    db.commit()

    logger.info(f"Password reset: {user.email} (id={user.user_id})")

    return ResetPasswordResponse(message="Password has been reset successfully. You can now log in with your new password.")


# ---------------------------------------------------------------------------
# Profile (authenticated)
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserProfileResponse)
def get_profile(current_user: User = Depends(get_current_user)):
    return UserProfileResponse(
        user=UserPublic(
            user_id=current_user.user_id,
            name=current_user.name,
            email=current_user.email,
            phone=current_user.phone,
            is_verified=current_user.is_verified,
        )
    )
