import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import HomePage from './components/HomePage';
import InterviewPage from './components/InterviewPage';
import AudioRecognitionTest from './components/AudioRecognitionTest';
import './styles/layout.css';
import './styles/theme.css';
import './styles/homepage.css';
import './styles/interview.css';

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/interview/:id" element={<InterviewPage />} />
        <Route path="/test/audio" element={<AudioRecognitionTest />} />
      </Routes>
    </Router>
  );
}