import { NavLink } from "react-router-dom";
import "./Navigation.css";

const ITEMS = [
  { to: "/generate", label: "Generate" },
  { to: "/history", label: "History" },
  { to: "/reference", label: "Reference" },
];

export function Navigation() {
  return (
    <nav className="app-nav" aria-label="Main navigation">
      {ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) => "app-nav__link" + (isActive ? " app-nav__link--active" : "")}
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
