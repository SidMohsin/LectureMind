import "./Card.css";

export default function Card({ children, className = "", ...rest }) {
  return (
    <div className={`card ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}
