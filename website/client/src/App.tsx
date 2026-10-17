import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/NotFound";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./contexts/ThemeContext";
import Home from "./pages/Home";
import Specification from "./pages/Specification";
import BookIndex from "./book/pages/BookIndex";
import BookChapter from "./book/pages/BookChapter";
import BookPrint from "./book/pages/BookPrint";
import Examples from "./pages/Examples";
import SpecViewer from "./pages/SpecViewer";
import GitHubRepo from "./pages/GitHubRepo";

function Router() {
  return (
    <Switch>
      <Route path={"/"} component={Home} />
      <Route path="/specification" component={Specification} />
      <Route path="/specification/:type" component={SpecViewer} />
      <Route path="/book" component={BookIndex} />
      <Route path="/book/print" component={BookPrint} />
      <Route path="/book/:slug" component={BookChapter} />
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
