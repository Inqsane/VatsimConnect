using System;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using RossCarlson.Vatsim.Vpilot.Plugins;
using RossCarlson.Vatsim.Vpilot.Plugins.Events;

namespace VatsimConnect
{
    public class Plugin : IPlugin
    {
        private static readonly HttpClient Http = CreateClient();
        private const string BridgeUrl = "http://127.0.0.1:39271/vpilot";
        private IBroker _broker;
        private string _callsign;
        private bool _networkConnected;
        private Timer _heartbeat;

        public string Name
        {
            get { return "VatsimConnect"; }
        }

        private static HttpClient CreateClient()
        {
            var client = new HttpClient();
            client.Timeout = TimeSpan.FromSeconds(2);
            return client;
        }

        public void Initialize(IBroker broker)
        {
            _broker = broker;
            _broker.NetworkConnected += OnNetworkConnected;
            _broker.NetworkDisconnected += OnNetworkDisconnected;
            _broker.PrivateMessageReceived += OnPrivateMessageReceived;
            _broker.RadioMessageReceived += OnRadioMessageReceived;
            _broker.SelcalAlertReceived += OnSelcalAlertReceived;
            _broker.PostDebugMessage("VatsimConnect plugin loaded");
            SendReady();
            _heartbeat = new Timer(OnHeartbeat, null, 1000, 3000);
        }

        private void OnHeartbeat(object state)
        {
            SendReady();
            if (_networkConnected)
            {
                var cs = string.IsNullOrEmpty(_callsign) ? "" : Escape(_callsign);
                var ignored = PostAsync(
                    "{\"type\":\"status\",\"connected\":true,\"callsign\":\"" + cs + "\"}"
                );
            }
        }

        private void SendReady()
        {
            var ignored = PostAsync("{\"type\":\"plugin\",\"status\":\"ready\"}");
        }

        private void OnNetworkConnected(object sender, NetworkConnectedEventArgs e)
        {
            _callsign = e.Callsign;
            _networkConnected = true;
            _broker.PostDebugMessage("VatsimConnect online as " + (_callsign ?? "?"));
            var ignored = PostAsync(
                "{\"type\":\"status\",\"connected\":true,\"callsign\":\"" + Escape(e.Callsign) + "\",\"cid\":\"" + Escape(e.Cid) + "\"}"
            );
        }

        private void OnNetworkDisconnected(object sender, EventArgs e)
        {
            _callsign = null;
            _networkConnected = false;
            var ignored = PostAsync("{\"type\":\"status\",\"connected\":false}");
        }

        private void OnPrivateMessageReceived(object sender, PrivateMessageReceivedEventArgs e)
        {
            var ignored = PostAsync(
                "{\"type\":\"message\",\"kind\":\"private\",\"from\":\"" + Escape(e.From) + "\",\"body\":\"" + Escape(e.Message) + "\"}"
            );
        }

        private void OnRadioMessageReceived(object sender, RadioMessageReceivedEventArgs e)
        {
            if (string.IsNullOrEmpty(_callsign))
            {
                return;
            }
            if (e.Message == null || e.Message.IndexOf(_callsign, StringComparison.OrdinalIgnoreCase) < 0)
            {
                return;
            }
            var ignored = PostAsync(
                "{\"type\":\"message\",\"kind\":\"radio\",\"from\":\"" + Escape(e.From) + "\",\"body\":\"" + Escape(e.Message) + "\"}"
            );
        }

        private void OnSelcalAlertReceived(object sender, SelcalAlertReceivedEventArgs e)
        {
            var ignored = PostAsync(
                "{\"type\":\"message\",\"kind\":\"selcal\",\"from\":\"" + Escape(e.From) + "\",\"body\":\"SELCAL alert\"}"
            );
        }

        private static string Escape(string value)
        {
            if (string.IsNullOrEmpty(value))
            {
                return "";
            }
            return value
                .Replace("\\", "\\\\")
                .Replace("\"", "\\\"")
                .Replace("\r", "\\r")
                .Replace("\n", "\\n")
                .Replace("\t", "\\t");
        }

        private async Task PostAsync(string json)
        {
            try
            {
                using (var content = new StringContent(json, Encoding.UTF8, "application/json"))
                {
                    await Http.PostAsync(BridgeUrl, content).ConfigureAwait(false);
                }
            }
            catch (Exception ex)
            {
                try
                {
                    _broker.PostDebugMessage("VatsimConnect bridge error: " + ex.Message);
                }
                catch
                {
                }
            }
        }
    }
}
