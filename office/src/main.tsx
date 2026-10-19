import {PortalGate} from './Connection';
import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import Dealer from './Dealer';
import Driver from './Driver';
import './style.css';
import './dealer.css';
createRoot(document.getElementById('root')!).render(<React.StrictMode><PortalGate>{window.location.pathname.startsWith('/fahrer') ? <Driver /> : window.location.pathname.startsWith('/haendler') ? <Dealer /> : <App />}</PortalGate></React.StrictMode>);

import './ipad.css';

import './driver.css';

import './connection.css';
