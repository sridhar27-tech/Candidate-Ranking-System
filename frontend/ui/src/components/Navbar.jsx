import React from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { FiCpu, FiHome, FiUsers, FiBarChart2 } from "react-icons/fi";

const Navbar = () => {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get("session");

  const withSession = (path) =>
    sessionId ? `${path}?session=${sessionId}` : path;

  const navItems = [
    { path: "/", label: "Home", icon: FiHome },
    { path: "/dashboard", label: "Dashboard", icon: FiUsers },
    { path: "/comparison", label: "Compare", icon: FiBarChart2 },
  ];

  return (
    <nav className="navbar">
      <div className="navbar-container">
        <Link to={withSession("/")} className="navbar-logo">
          <FiCpu className="logo-icon" />
          <span className="logo-text">RedRob AI</span>
        </Link>

        <div className="navbar-links">
          {navItems.map(({ path, label, icon: Icon }) => (
            <Link
              key={path}
              to={withSession(path)}
              className={`navbar-link${location.pathname === path ? " active" : ""}`}
            >
              <Icon className="nav-icon" />
              <span>{label}</span>
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
