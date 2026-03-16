import { type ButtonHTMLAttributes, forwardRef } from "react";
import { LoadingSpinner } from "./LoadingSpinner";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger";
  isLoading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { variant = "primary", isLoading, disabled, children, className = "", ...props },
    ref
  ) => {
    const base =
      "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50";

    const variants = {
      primary:
        "bg-blue-600 text-white hover:bg-blue-700 focus-visible:ring-blue-600",
      secondary:
        "border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 focus-visible:ring-gray-400",
      danger:
        "bg-red-600 text-white hover:bg-red-700 focus-visible:ring-red-600",
    };

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={`${base} ${variants[variant]} ${className}`}
        {...props}
      >
        {isLoading && <LoadingSpinner size="sm" />}
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";
