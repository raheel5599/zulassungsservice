import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import Dealer from './Dealer';
import './style.css';
import './dealer.css';
createRoot(document.getElementById('root')!).render(<React.StrictMode>{window.location.pathname.startsWith('/haendler') ? <Dealer /> : <App />}</React.StrictMode>);

import './ipad.css';
