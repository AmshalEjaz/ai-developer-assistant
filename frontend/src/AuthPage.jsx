import { useState } from "react";
import "./AuthPage.css";

const API_URL = "http://127.0.0.1:8000";

function getErrorMessage(data) {
  if (typeof data?.detail === "string") {
    return data.detail;
  }

  if (Array.isArray(data?.detail) && data.detail.length > 0) {
    return data.detail[0]?.msg || "Please check your information.";
  }

  return "Something went wrong. Please try again.";
}

function AuthPage({ onAuthenticated }) {
  const [mode, setMode] = useState("login");

  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
  });

  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const updateField = (event) => {
    const { name, value } = event.target;

    setForm((current) => ({
      ...current,
      [name]: value,
    }));

    setError("");
  };

  const loginUser = async () => {
    const response = await fetch(`${API_URL}/api/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        email: form.email.trim(),
        password: form.password,
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(getErrorMessage(data));
    }

    localStorage.setItem(
      "devpilot_token",
      data.access_token
    );

    onAuthenticated(data.user);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    setError("");
    setIsLoading(true);

    try {
      if (mode === "signup") {
        const signupResponse = await fetch(
          `${API_URL}/api/auth/signup`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              username: form.username.trim(),
              email: form.email.trim(),
              password: form.password,
            }),
          }
        );

        const signupData =
          await signupResponse.json();

        if (!signupResponse.ok) {
          throw new Error(
            getErrorMessage(signupData)
          );
        }
      }

      await loginUser();
    } catch (err) {
      setError(
        err.message ||
          "Unable to continue. Please try again."
      );
    } finally {
      setIsLoading(false);
    }
  };

  const changeMode = (nextMode) => {
    setMode(nextMode);

    setError("");

    setForm({
      username: "",
      email: "",
      password: "",
    });
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <div className="auth-logo">✦</div>

          <div>
            <h1>DevPilot</h1>
            <p>AI Developer Assistant</p>
          </div>
        </div>

        <div className="auth-heading">
          <span>
            {mode === "login"
              ? "WELCOME BACK"
              : "GET STARTED"}
          </span>

          <h2>
            {mode === "login"
              ? "Sign in to your workspace"
              : "Create your account"}
          </h2>

          <p>
            {mode === "login"
              ? "Continue your development workspace."
              : "Create an account to start using DevPilot."}
          </p>
        </div>

        <form
          className="auth-form"
          onSubmit={handleSubmit}
        >
          {mode === "signup" && (
            <label>
              <span>Username</span>

              <input
                type="text"
                name="username"
                value={form.username}
                onChange={updateField}
                placeholder="Your username"
                minLength="3"
                maxLength="50"
                required
                autoComplete="username"
              />
            </label>
          )}

          <label>
            <span>Email</span>

            <input
              type="email"
              name="email"
              value={form.email}
              onChange={updateField}
              placeholder="you@example.com"
              required
              autoComplete="email"
            />
          </label>

          <label>
            <span>Password</span>

            <input
              type="password"
              name="password"
              value={form.password}
              onChange={updateField}
              placeholder="Minimum 8 characters"
              minLength="8"
              maxLength="128"
              required
              autoComplete={
                mode === "login"
                  ? "current-password"
                  : "new-password"
              }
            />
          </label>

          {error && (
            <div className="auth-error">
              {error}
            </div>
          )}

          <button
            className="auth-submit"
            type="submit"
            disabled={isLoading}
          >
            {isLoading
              ? "Please wait..."
              : mode === "login"
              ? "Sign in"
              : "Create account"}
          </button>
        </form>

        <div className="auth-switch">
          {mode === "login" ? (
            <>
              <span>Don't have an account?</span>

              <button
                type="button"
                onClick={() =>
                  changeMode("signup")
                }
              >
                Create account
              </button>
            </>
          ) : (
            <>
              <span>Already have an account?</span>

              <button
                type="button"
                onClick={() =>
                  changeMode("login")
                }
              >
                Sign in
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default AuthPage;