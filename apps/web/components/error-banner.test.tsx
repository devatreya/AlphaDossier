import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ErrorBanner } from "./error-banner";

describe("ErrorBanner", () => {
  it("renders the title inside an alert role", () => {
    render(<ErrorBanner title="Could not load thesis" />);
    const alert = screen.getByRole("alert");
    expect(alert).toBeInTheDocument();
    expect(alert).toHaveTextContent(/could not load thesis/i);
  });

  it("renders detail when provided", () => {
    render(<ErrorBanner title="Boom" detail="something exploded" />);
    expect(screen.getByText(/something exploded/)).toBeInTheDocument();
  });

  it("renders without detail", () => {
    render(<ErrorBanner title="Generic error" />);
    expect(screen.getByText("Generic error")).toBeInTheDocument();
  });
});
