import "./Button.css";

const VARIANT_CLASS = {
  primary: "btn btn--primary",
  secondary: "btn btn--secondary",
  tertiary: "btn btn--tertiary",
  destructive: "btn btn--destructive",
};

export default function Button({
  variant = "primary",
  as: Component = "button",
  className = "",
  children,
  ...rest
}) {
  const classes = `${VARIANT_CLASS[variant] || VARIANT_CLASS.primary} ${className}`.trim();
  return (
    <Component className={classes} {...rest}>
      {children}
    </Component>
  );
}
