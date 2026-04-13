declare module '@react-native-community/netinfo' {
  interface NetInfoState {
    isConnected: boolean | null;
    isInternetReachable: boolean | null;
  }

  type NetInfoChangeHandler = (state: NetInfoState) => void;

  interface NetInfoModule {
    addEventListener(listener: NetInfoChangeHandler): () => void;
    fetch(): Promise<NetInfoState>;
  }

  const NetInfo: NetInfoModule;
  export default NetInfo;
}
