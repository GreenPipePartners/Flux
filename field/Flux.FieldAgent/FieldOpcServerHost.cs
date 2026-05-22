using Opc.Ua;
using Opc.Ua.Configuration;

namespace Flux.FieldAgent;

public sealed class FieldOpcServerHost(ILogger<FieldOpcServerHost> logger)
{
    private ApplicationInstance? application;
    private FieldOpcServer? server;

    public async Task StartAsync(FieldConfig config, FieldAgentOptions options, CancellationToken cancellationToken)
    {
        if (server is not null)
        {
            return;
        }

        var endpointUrl = FirstEndpointUrl(config) ?? options.EndpointUrl;
        var configuration = await BuildValidatedConfigurationAsync(
            endpointUrl,
            options.CertificateStorePath,
            cancellationToken).ConfigureAwait(false);
        application = BuildApplicationInstance(configuration);
        server = new FieldOpcServer(config);
        await application.StartAsync(server).ConfigureAwait(false);
        logger.LogInformation("Flux Field OPC UA server started endpoint={EndpointUrl}", endpointUrl);
    }

    public void Stop()
    {
        server?.StopAsync(CancellationToken.None).AsTask().GetAwaiter().GetResult();
        server = null;
        application = null;
    }

    private static string? FirstEndpointUrl(FieldConfig config)
    {
        return config.Endpoints.FirstOrDefault(endpoint => !string.IsNullOrWhiteSpace(endpoint.EndpointUrl))?.EndpointUrl;
    }

    private static ApplicationConfiguration BuildApplicationConfiguration(
        string endpointUrl,
        string certificateStorePath)
    {
        var ownStore = Path.Combine(certificateStorePath, "own");
        var trustedStore = Path.Combine(certificateStorePath, "trusted");
        var issuerStore = Path.Combine(certificateStorePath, "issuers");
        var rejectedStore = Path.Combine(certificateStorePath, "rejected");

        return new ApplicationConfiguration
        {
            ApplicationName = "Flux Field Agent",
            ApplicationUri = "urn:flux:field",
            ProductUri = "urn:flux:field",
            ApplicationType = ApplicationType.Server,
            SecurityConfiguration = new SecurityConfiguration
            {
                ApplicationCertificate = new CertificateIdentifier
                {
                    StoreType = CertificateStoreType.Directory,
                    StorePath = ownStore,
                    SubjectName = "CN=Flux Field Agent",
                },
                TrustedPeerCertificates = new CertificateTrustList
                {
                    StoreType = CertificateStoreType.Directory,
                    StorePath = trustedStore,
                },
                TrustedIssuerCertificates = new CertificateTrustList
                {
                    StoreType = CertificateStoreType.Directory,
                    StorePath = issuerStore,
                },
                RejectedCertificateStore = new CertificateTrustList
                {
                    StoreType = CertificateStoreType.Directory,
                    StorePath = rejectedStore,
                },
                AutoAcceptUntrustedCertificates = true,
                AddAppCertToTrustedStore = true,
            },
            ServerConfiguration = new ServerConfiguration
            {
                BaseAddresses = { endpointUrl },
                SecurityPolicies =
                {
                    new ServerSecurityPolicy
                    {
                        SecurityMode = MessageSecurityMode.None,
                        SecurityPolicyUri = SecurityPolicies.None,
                    }
                },
                UserTokenPolicies =
                {
                    new UserTokenPolicy(UserTokenType.Anonymous),
                },
                DiagnosticsEnabled = false,
                MaxSessionCount = 100,
                MinSessionTimeout = 10_000,
                MaxSessionTimeout = 3_600_000,
                MaxBrowseContinuationPoints = 10,
                MaxQueryContinuationPoints = 10,
                MaxHistoryContinuationPoints = 10,
                MaxRequestAge = 600_000,
                MinPublishingInterval = 100,
                MaxPublishingInterval = 3_600_000,
                PublishingResolution = 50,
                MaxSubscriptionLifetime = 3_600_000,
                MaxMessageQueueSize = 100,
                MaxNotificationQueueSize = 100,
                MaxNotificationsPerPublish = 1_000,
            },
            TransportQuotas = new TransportQuotas
            {
                OperationTimeout = 120_000,
                MaxStringLength = 1_048_576,
                MaxByteStringLength = 1_048_576,
                MaxArrayLength = 65_535,
                MaxMessageSize = 4_194_304,
                MaxBufferSize = 65_535,
                ChannelLifetime = 300_000,
                SecurityTokenLifetime = 3_600_000,
            },
            TraceConfiguration = new TraceConfiguration(),
            DisableHiResClock = false,
        };
    }

    private async Task<ApplicationConfiguration> BuildValidatedConfigurationAsync(
        string endpointUrl,
        string certificateStorePath,
        CancellationToken cancellationToken)
    {
        var configuration = BuildApplicationConfiguration(endpointUrl, certificateStorePath);
        await configuration.ValidateAsync(ApplicationType.Server).ConfigureAwait(false);
        try
        {
            await BuildApplicationInstance(configuration)
                .CheckApplicationInstanceCertificatesAsync(false, 0, cancellationToken)
                .ConfigureAwait(false);
            return configuration;
        }
        catch (Exception exc) when (LooksLikeInvalidGeneratedCertificate(exc))
        {
            var ownStore = Path.Combine(certificateStorePath, "own");
            logger.LogWarning(exc, "Generated OPC UA application certificate is invalid; recreating certificate store at {OwnStore}", ownStore);
            DeleteDirectoryIfExists(ownStore);

            configuration = BuildApplicationConfiguration(endpointUrl, certificateStorePath);
            await configuration.ValidateAsync(ApplicationType.Server).ConfigureAwait(false);
            await BuildApplicationInstance(configuration)
                .CheckApplicationInstanceCertificatesAsync(false, 0, cancellationToken)
                .ConfigureAwait(false);
            return configuration;
        }
    }

    private static ApplicationInstance BuildApplicationInstance(ApplicationConfiguration configuration)
    {
        return new ApplicationInstance
        {
            ApplicationName = "Flux Field Agent",
            ApplicationType = ApplicationType.Server,
            ApplicationConfiguration = configuration,
        };
    }

    private static bool LooksLikeInvalidGeneratedCertificate(Exception exc)
    {
        var message = exc.ToString();
        return message.Contains("certificate", StringComparison.OrdinalIgnoreCase)
            && message.Contains("invalid", StringComparison.OrdinalIgnoreCase);
    }

    private static void DeleteDirectoryIfExists(string path)
    {
        if (Directory.Exists(path))
        {
            Directory.Delete(path, recursive: true);
        }
    }
}
