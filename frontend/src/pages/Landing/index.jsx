import { Link } from "react-router-dom";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import Footer from "../../components/layout/Footer";
import { useAuth } from "../../auth/AuthContext";
import "./Landing.css";

const WORKFLOW_STEPS = ["Lecture", "Transcription", "Structure", "Search / Retrieval", "Grounded Answers"];

const CAPABILITIES = [
  {
    title: "Timestamped transcript",
    description: "Every spoken segment is preserved with accurate start and end timestamps.",
  },
  {
    title: "Chapters",
    description: "Lectures are broken into meaningful sections you can jump to directly.",
  },
  {
    title: "Key concepts",
    description: "Core concepts, definitions and keywords are extracted from what was actually taught.",
  },
  {
    title: "Searchable lecture content",
    description: "Find a specific explanation across your whole library without replaying anything.",
  },
  {
    title: "Grounded Q&A",
    description: "Ask a question and get an answer tied to the lecture's own evidence and timestamps.",
  },
];

const USE_CASES = [
  "Revising for an exam without rewatching a full lecture",
  "Finding the one explanation you half-remember",
  "Understanding the structure of a long, dense lecture",
  "Jumping straight back to a specific moment",
];

export default function Landing() {
  const { status } = useAuth();

  return (
    <div>
      <header className="landing-header">
        <div className="landing-header__inner">
          <Link to="/" className="landing-header__brand">
            <span className="landing-header__logo-mark">T.</span>
            <span>LectureMind</span>
          </Link>
          <div className="landing-header__actions">
            {status === "authenticated" ? (
              <Button as={Link} to="/dashboard" variant="primary">
                Go to Dashboard
              </Button>
            ) : (
              <>
                <Button as={Link} to="/login" variant="secondary">
                  Log In
                </Button>
                <Button as={Link} to="/signup" variant="primary">
                  Get Started
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      <section className="landing-hero">
        <h1 className="landing-hero__title">Turn lectures into knowledge you can actually use.</h1>
        <p className="landing-hero__subtitle">
          LectureMind converts recorded lectures into a timestamped transcript, structured chapters and concepts,
          and lecture-grounded question answering — so nothing you sat through gets lost.
        </p>
        <div className="landing-hero__actions">
          <Button as={Link} to="/signup" variant="primary">
            Get Started
          </Button>
          <Button as="a" href="#how-it-works" variant="secondary">
            See how it works
          </Button>
        </div>
      </section>

      <section className="landing-section" id="how-it-works">
        <h2 className="landing-section__heading">How It Works</h2>
        <p className="landing-section__subheading">
          A lecture goes through the same pipeline every time: transcription, structure, retrieval, and grounded
          answers.
        </p>
        <div className="landing-flow">
          {WORKFLOW_STEPS.map((step, index) => (
            <span key={step} style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <span className="landing-flow__step">{step}</span>
              {index < WORKFLOW_STEPS.length - 1 && <span className="landing-flow__arrow">→</span>}
            </span>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <h2 className="landing-section__heading">Core Capabilities</h2>
        <p className="landing-section__subheading">
          Every capability below produces something you can see, search or click through to a moment in the
          lecture.
        </p>
        <div className="landing-grid">
          {CAPABILITIES.map((capability) => (
            <Card key={capability.title}>
              <h3>{capability.title}</h3>
              <p>{capability.description}</p>
            </Card>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <h2 className="landing-section__heading">Use Cases</h2>
        <div className="landing-grid">
          {USE_CASES.map((useCase) => (
            <Card key={useCase}>
              <p>{useCase}</p>
            </Card>
          ))}
        </div>
      </section>

      <div className="landing-cta">
        <h2 className="landing-cta__title">Start turning your lectures into a knowledge base.</h2>
        <p className="landing-cta__description">Sign up and upload your first lecture.</p>
        <Button as={Link} to="/signup" variant="primary">
          Get Started
        </Button>
      </div>

      <Footer />
    </div>
  );
}
