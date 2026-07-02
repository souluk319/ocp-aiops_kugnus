export const FLAG_LIGHTSPEED_PLUGIN = 'LIGHTSPEED_PLUGIN';

export const enableLightspeedPluginFlag = (setFeatureFlag: (flag: string, enabled: boolean) => void): void => {
  setFeatureFlag(FLAG_LIGHTSPEED_PLUGIN, true);
};
