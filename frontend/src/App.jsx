import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import LandingPage from './LandingPage';
import PropertyVerification from './PropertyVerification';
import Questionnaire from './Questionnaire';
import Dashboard from './Dashboard';
import UpgradePage from './UpgradePage';
import './index.css';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/verify" element={<PropertyVerification />} />
        <Route path="/questionnaire" element={<Questionnaire />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/upgrade" element={<UpgradePage />} />
      </Routes>
    </Router>
  );
}

export default App;
