import { type ComponentProps, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type CardProps = ComponentProps<"div"> & {
  children: ReactNode;
  className?: string;
};

export function Card({ children, className, ...props }: CardProps) {
  return (
    <div className={cn("rounded-lg border border-[#333333] bg-[#2b2b2b]", className)} {...props}>
      {children}
    </div>
  );
}
