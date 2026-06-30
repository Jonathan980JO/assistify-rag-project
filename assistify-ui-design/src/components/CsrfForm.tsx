"use client";

import { FormHTMLAttributes, ReactNode, useEffect, useState } from "react";
import { getCSRFToken } from "@/src/lib/apiClient";

interface CsrfFormProps extends FormHTMLAttributes<HTMLFormElement> {
  action: string;
  children: ReactNode;
}

export function CsrfForm({ action, method = "post", children, ...rest }: CsrfFormProps) {
  const [token, setToken] = useState("");

  useEffect(() => {
    setToken(getCSRFToken() ?? "");
  }, []);

  return (
    <form action={action} method={method} {...rest}>
      <input type="hidden" name="csrf_token" value={token} />
      {children}
    </form>
  );
}
