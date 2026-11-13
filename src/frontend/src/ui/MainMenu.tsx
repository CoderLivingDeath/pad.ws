import React, { useState } from 'react';

import type { ExcalidrawImperativeAPI } from '@atyrode/excalidraw/types';
import type { MainMenu as MainMenuType } from '@atyrode/excalidraw';

import { LogOut, SquarePlus, LayoutDashboard, User, Text, Settings, Terminal, FileText, FlaskConical } from 'lucide-react';
import md5 from 'crypto-js/md5';

// Components
import SettingsDialog from './SettingsDialog';

import { useLogout } from '../hooks/useLogout';
import { useAuthStatus } from '../hooks/useAuthStatus';

import { ExcalidrawElementFactory, PlacementMode } from '../lib/elementFactory';
import { INITIAL_APP_DATA } from '../constants';
import { capture } from '../lib/posthog';
import "./MainMenu.scss";
import AccountDialog from './AccountDialog';


// Function to generate gravatar URL
const getGravatarUrl = (email: string, size = 32) => {
  const hash = md5(email.toLowerCase().trim()).toString();
  return `https://www.gravatar.com/avatar/${hash}?s=${size}&d=identicon`;
};

interface MainMenuConfigProps {
  MainMenu: typeof MainMenuType;
  excalidrawAPI: ExcalidrawImperativeAPI | null;
}

export const MainMenuConfig: React.FC<MainMenuConfigProps> = ({
  MainMenu,
  excalidrawAPI,
}) => {
  const [showAccountModal, setShowAccountModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);

  const { mutate: logoutMutation, isPending: isLoggingOut } = useLogout();
  const { user, isLoading, isError } = useAuthStatus();

  let username = "";
  let email = "";
  if (isLoading) {
    username = "Loading...";
  } else if (isError || !user?.username) {
    username = "Unknown";
  } else {
    username = user.username;
    email = user.email || "";
  }

  const handleDashboardButtonClick = () => {
    if (!excalidrawAPI) return;
    
    const dashboardElement = ExcalidrawElementFactory.createEmbeddableElement({
      link: "!dashboard",
      width: 360,
      height: 360
    });
    
    ExcalidrawElementFactory.placeInScene(dashboardElement, excalidrawAPI, {
      mode: PlacementMode.NEAR_VIEWPORT_CENTER,
      bufferPercentage: 10,
      scrollToView: true
    });
  };

  const handleInsertButtonClick = () => {
    if (!excalidrawAPI) return;
    
    const buttonElement = ExcalidrawElementFactory.createEmbeddableElement({
      link: "!button",
      width: 460,
      height: 80
    });
    
    ExcalidrawElementFactory.placeInScene(buttonElement, excalidrawAPI, {
      mode: PlacementMode.NEAR_VIEWPORT_CENTER,
      bufferPercentage: 10,
      scrollToView: true
    });
  };
  
  const handleEditorClick = () => {
    if (!excalidrawAPI) return;
    
    const editorElement = ExcalidrawElementFactory.createEmbeddableElement({
      link: "!editor",
      width: 800,
      height: 500
    });
    
    ExcalidrawElementFactory.placeInScene(editorElement, excalidrawAPI, {
      mode: PlacementMode.NEAR_VIEWPORT_CENTER,
      bufferPercentage: 10,
      scrollToView: true
    });
  };
  
  const handleTerminalClick = () => {
    if (!excalidrawAPI) return;
    
    const terminalElement = ExcalidrawElementFactory.createEmbeddableElement({
      link: "!terminal",
      width: 800,
      height: 500
    });
    
    ExcalidrawElementFactory.placeInScene(terminalElement, excalidrawAPI, {
      mode: PlacementMode.NEAR_VIEWPORT_CENTER,
      bufferPercentage: 10,
      scrollToView: true
    });
  };

  const handleSettingsClick = () => {
    setShowSettingsModal(true);
  };

  const handleCloseSettingsModal = () => {
    setShowSettingsModal(false);
  };
  
  const handleAccountClick = () => {
    setShowAccountModal(true);
  };

  const handleLogout = () => {
    capture('logout_clicked');

    logoutMutation(undefined, {
      onSuccess: (data) => {
        // Navigate to the IdP end-session URL returned by the backend. A full
        // redirect is required because the landing page is gated and there is
        // no anonymous fallback after the Pad session cookie is cleared.
        window.location.assign(data.logout_url);
      },
      onError: (error) => {
        console.error("[pad.ws] Logout failed in MainMenu component:", error.message);
      }
    });

    excalidrawAPI.updateScene(INITIAL_APP_DATA);

  };

  return (
    <>
      {showAccountModal && (
        <AccountDialog 
          excalidrawAPI={excalidrawAPI} 
          onClose={() => setShowAccountModal(false)} 
        />
      )}
      {showSettingsModal && (
        <SettingsDialog
          excalidrawAPI={excalidrawAPI}
          onClose={handleCloseSettingsModal}
        />
      )}
      <MainMenu>
        <div className="main-menu__top-row">
          <span className="main-menu__label" style={{ gap: 0.2 }}>
            {email && (
              <img 
                src={getGravatarUrl(email)} 
                alt={username} 
                className="main-menu__gravatar" 
                width={20} 
                height={20} 
                style={{ borderRadius: '50%', marginRight: '8px' }}
              />
            )}
            <span className="main-menu__label-username">{username}</span>
          </span>
        </div>
      <MainMenu.Separator />

      <MainMenu.Group title="Files">
        <MainMenu.DefaultItems.LoadScene />
        <MainMenu.DefaultItems.Export />
        <MainMenu.DefaultItems.SaveAsImage />
        <MainMenu.DefaultItems.ClearCanvas />
      </MainMenu.Group>
      
      <MainMenu.Separator />
    
      <MainMenu.Group title="Tools">
        <MainMenu.Item
          icon={<Text />}
          onClick={handleEditorClick}
        >
          Code Editor
        </MainMenu.Item>
        <MainMenu.Item
          icon={<Terminal />}
          onClick={handleTerminalClick}
        >
          Terminal
        </MainMenu.Item>
        <MainMenu.Item
          icon={<LayoutDashboard />}
          onClick={handleDashboardButtonClick}
        >
          Dashboard
        </MainMenu.Item>
        <MainMenu.Item
          icon={<SquarePlus />}
          onClick={handleInsertButtonClick}
        >
          Action Button
        </MainMenu.Item>
      </MainMenu.Group>
      
      <MainMenu.Separator />
      
      <MainMenu.Item
          icon={<User />}
          onClick={handleAccountClick}
        >
          Account
        </MainMenu.Item>
      
      <MainMenu.Item
          icon={<Settings />}
          onClick={handleSettingsClick}
        >
          Settings
        </MainMenu.Item>
      
      <MainMenu.Item
          icon={<LogOut />}
          onClick={handleLogout}
          disabled={isLoggingOut} // Disable button while logout is in progress
        >
          {isLoggingOut ? "Logging out..." : "Logout"}
        </MainMenu.Item>
      
    </MainMenu>
    </>
  );
};
