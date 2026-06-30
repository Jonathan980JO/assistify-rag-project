const ERROR_MESSAGES: Record<string, string> = {
  rate_limit: "Too many requests. Please try again later.",
  invalid_email: "Please enter a valid email address.",
  invalid_username: "Username format is invalid.",
  passwords_dont_match: "Passwords do not match.",
  weak_password: "Password does not meet strength requirements.",
  username_exists: "That username is already taken.",
  email_exists: "That email is already registered.",
  invalid_password: "Password could not be processed.",
  server_error: "Server error. Please try again.",
  invalid_or_expired_otp: "Invalid or expired verification code.",
};

/** Map legacy error codes or pass through human-readable server messages. */
export function authFlashMessage(code: string | null | undefined): string | null {
  if (!code) return null;
  if (ERROR_MESSAGES[code]) return ERROR_MESSAGES[code];
  try {
    return decodeURIComponent(code.replace(/\+/g, " "));
  } catch {
    return code.replace(/\+/g, " ");
  }
}
