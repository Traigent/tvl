import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/NotFound";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./contexts/ThemeContext";
import Home from "./pages/Home";
import Specification from "./pages/Specification";
import BookTbd from "./pages/BookTbd";
import BookMaterial from "./pages/BookMaterial";
import BookMaterials from "./pages/BookMaterials";
import BookPattern from "./pages/BookPattern";
import BookPatterns from "./pages/BookPatterns";
import Examples from "./pages/Examples";
import Chapter from "./pages/Chapter";
import Section from "./pages/Section";
import SpecViewer from "./pages/SpecViewer";
import GitHubRepo from "./pages/GitHubRepo";

function Router() {
  return (
    <Switch>
      <Route path={"/"} component={Home} />
      <Route path="/specification" component={Specification} />
      <Route path="/specification/:type" component={SpecViewer} />
      <Route path="/book" component={BookTbd} />
      <Route path="/book/materials" component={BookMaterials} />
      <Route path="/book/materials/:materialSlug" component={BookMaterial} />
      <Route path="/book/patterns" component={BookPatterns} />
      <Route path="/book/patterns/:patternSlug" component={BookPattern} />
      <Route path="/book/chapter/:chapterSlug" component={Chapter} />
      <Route path="/book/chapter/:chapterSlug/section/:sectionSlug" component={Section} />
      <Route path="/examples" component={Examples} />
      <Route path="/github" component={GitHubRepo} />
      <Route path={"/404"} component={NotFound} />
      {/* Final fallback route */}
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider defaultTheme="dark">
        <TooltipProvider>
          <Toaster />
          <Router />
        </TooltipProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
